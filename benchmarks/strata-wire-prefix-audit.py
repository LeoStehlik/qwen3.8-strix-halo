#!/usr/bin/env python3
"""Offline, content-private audit of incoming Strata HTTP prompts.

Reads tcpdump classic PCAP from a RAW IPv4 interface. Reassembles TCP, rejects
conflicting retransmissions/gaps, and extracts complete Content-Length HTTP
requests. Never sends a model request. HTTP headers (including credentials) are
not exported. Raw request bodies and token IDs belong in a private directory;
the summary contains only counts, positions and hashes.

Use the packaged Strata Python and the exact serving tokenizer/template.
Only ordinary text chat-completions requests are supported. Token counts must
be reconciled with the serving metrics before drawing cache conclusions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys


def sha(value):
    data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    return hashlib.sha256(data).hexdigest()


def lcp(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))


def read_requests(path):
    data = path.read_bytes()
    if len(data) < 24:
        return [], {'incomplete_capture_header': True}
    magic = data[:4]
    orders = {b'\xd4\xc3\xb2\xa1': ('<', 1e6), b'\xa1\xb2\xc3\xd4': ('>', 1e6),
              b'\x4d\x3c\xb2\xa1': ('<', 1e9), b'\xa1\xb2\x3c\x4d': ('>', 1e9)}
    if magic not in orders:
        raise ValueError('Only classic PCAP is supported')
    order, resolution = orders[magic]
    link = struct.unpack_from(order + 'I', data, 20)[0]
    if link not in (12, 101):
        raise ValueError(f'Expected RAW IP link type; got {link}')
    streams, current = [], {}
    pos, packets, partial = 24, 0, False
    while pos + 16 <= len(data):
        sec, usec, size, original = struct.unpack_from(order + 'IIII', data, pos)
        pos += 16
        if pos + size > len(data):
            partial = True
            break
        packet = data[pos:pos + size]
        pos += size
        packets += 1
        if size != original:
            raise ValueError('Truncated packet: increase capture snap length')
        if len(packet) < 20 or packet[0] >> 4 != 4 or packet[9] != 6:
            continue
        ihl = (packet[0] & 15) * 4
        total = struct.unpack_from('!H', packet, 2)[0]
        if struct.unpack_from('!H', packet, 6)[0] & 0x3fff:
            raise ValueError('Fragmented IPv4 is unsupported')
        if total > len(packet) or ihl < 20 or total < ihl + 20:
            raise ValueError('Incomplete IPv4/TCP packet')
        source, dest, seq = struct.unpack_from('!HHI', packet, ihl)
        hlen = (packet[ihl + 12] >> 4) * 4
        if hlen < 20 or ihl + hlen > total:
            raise ValueError('Malformed TCP header')
        flags = packet[ihl + 13]
        key = (packet[12:20], source, dest)
        syn = bool(flags & 2)
        if key not in current or syn and current[key]['syn'] != seq:
            current[key] = {'syn': seq if syn else None, 'segments': [], 'time': sec + usec / resolution}
            streams.append(current[key])
        payload = packet[ihl + hlen:total]
        if payload:
            current[key]['segments'].append(((seq + int(syn)) & 0xffffffff, payload, sec + usec / resolution))
    requests, gaps = [], 0
    for stream in streams:
        segments = stream['segments']
        if not segments:
            continue
        # Signed offsets handle the one sequence-number wrap possible in this
        # bounded capture. Each stream must contain fewer than 2 GiB of payload.
        anchor = segments[0][0]
        ordered = sorted((((seq - anchor + 2**31) % 2**32 - 2**31, body, t)
                          for seq, body, t in segments), key=lambda x: x[0])
        start = ordered[0][0]
        body = bytearray()
        times = []
        valid = True
        for off, chunk, t in ordered:
            off -= start
            if off > len(body):
                gaps += 1
                valid = False
                break
            overlap = min(len(chunk), len(body) - off)
            if body[off:off + overlap] != chunk[:overlap]:
                raise ValueError('Conflicting TCP retransmission')
            if overlap < len(chunk):
                times.append((len(body), t))
                body.extend(chunk[overlap:])
        if not valid:
            continue
        cursor = 0
        while cursor < len(body):
            end = body.find(b'\r\n\r\n', cursor)
            if end < 0:
                break
            lines = bytes(body[cursor:end]).split(b'\r\n')
            parts = lines[0].split(b' ')
            if len(parts) != 3 or parts[0] not in (b'POST', b'GET', b'HEAD') or not parts[2].startswith(b'HTTP/'):
                # Capture began in the middle of a request: never guess a body.
                break
            headers = {}
            for line in lines[1:]:
                k, sep, v = line.partition(b':')
                if not sep:
                    raise ValueError('Invalid HTTP header')
                headers[k.strip().lower()] = v.strip()
            if b'transfer-encoding' in headers:
                raise ValueError('Chunked HTTP requests unsupported; use another capture decoder')
            n = int(headers.get(b'content-length', b'0'))
            begin = end + 4
            if begin + n > len(body):
                break
            if parts[0] == b'POST' and parts[1].split(b'?')[0] == b'/v1/chat/completions':
                raw = bytes(body[begin:begin + n])
                request = json.loads(raw)
                t = next((t for off, t in reversed(times) if off <= cursor), stream['time'])
                requests.append({'time': t, 'body_sha256': sha(raw), 'request': request})
            cursor = begin + n
    requests.sort(key=lambda r: r['time'])
    return requests, {'packets': packets, 'streams': len(streams), 'streams_with_gaps': gaps,
                      'incomplete_last_packet': partial}


def first_change(a, b, path=''):
    if type(a) is not type(b):
        return {'path': path, 'kind': 'type'}
    if isinstance(a, dict):
        for k in a:
            if k not in b:
                return {'path': path + '/' + k, 'kind': 'removed'}
            d = first_change(a[k], b[k], path + '/' + k)
            if d:
                return d
        for k in b:
            if k not in a:
                return {'path': path + '/' + k, 'kind': 'added'}
    elif isinstance(a, list):
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_change(x, y, path + '/' + str(i))
            if d:
                return d
        if len(a) != len(b):
            return {'path': path, 'kind': 'length', 'before': len(a), 'after': len(b)}
    elif a != b:
        d = {'path': path, 'kind': 'value'}
        if isinstance(a, str):
            d.update(first_changed_char=lcp(a, b), before_chars=len(a), after_chars=len(b))
        return d
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pcap', type=Path, required=True)
    ap.add_argument('--terminal', type=Path, required=True)
    ap.add_argument('--tokenizer', type=Path, required=True)
    ap.add_argument('--profile', type=Path, required=True)
    ap.add_argument('--private-out', type=Path, required=True)
    ap.add_argument('--summary-out', type=Path, required=True)
    args = ap.parse_args()
    os.umask(0o077)
    args.private_out.mkdir(parents=True, exist_ok=True, mode=0o700)
    records, capture = read_requests(args.pcap)
    sys.path[:0] = [str(args.terminal), str(args.terminal / 'tools')]
    from serve import frontend
    from serve.frontend import ChatTemplate, openai_to_messages, literal_tags, mark_think_literals, unmark_think_literals
    from serve.server import Service
    from strata_tokenizer import Tokenizer
    cfg = json.loads(args.profile.read_text())
    frontend.ENV_TO_USER = cfg.get('env_to_user', False)
    vocab = json.loads((args.tokenizer / 'vocab.json').read_text())
    tokens = [None] * len(vocab)
    for token, i in vocab.items():
        tokens[i] = token
    tc = json.loads((args.tokenizer / 'tokenizer.json').read_text())
    tok = Tokenizer(tokens, (args.tokenizer / 'merges.txt').read_text().split('\n'),
                    json.loads((args.tokenizer / 'token_type.json').read_text()),
                    tc.get('pre') or 'qwen35', tc.get('special_ids') or None)
    # No Service constructor, engine, network, or model load is involved.
    svc = Service.__new__(Service)
    svc.tok = tok
    svc.template = ChatTemplate(args.tokenizer / 'chat_template.jinja')
    svc.literals = literal_tags(getattr(tok, 'control_tokens', ()))
    svc.prompts = None
    svc.effort_end = cfg.get('effort_position', 'start') == 'end'
    shared = args.profile.with_suffix('').with_name(args.profile.stem + '.shared-settings.json')
    svc.shared = json.loads(shared.read_text()) if shared.exists() else {}
    svc.config_effort = cfg.get('reasoning_effort')
    rows, previous_ids, previous_req = [], None, None
    for i, record in enumerate(records):
        req = record['request']
        key = f'{i:03d}-{record["body_sha256"][:12]}'
        (args.private_out / (key + '.request.json')).write_text(json.dumps(req, ensure_ascii=False, indent=2))
        req = svc.with_shared(req, 'openai')
        if req.get('response_format') or req.get('tool_choice') not in (None, 'auto', 'none') or req.get('strata_mcp'):
            raise ValueError('Unsupported structured/forced/MCP request')
        messages, tools, kwargs = openai_to_messages(req)
        if req.get('tool_choice') == 'none':
            tools = None
        for m in messages:
            if isinstance(m.get('content'), list) and any(p.get('type') != 'text' for p in m['content']):
                raise ValueError('Only text messages supported')
        ids = svc.encode_prompt(messages, tools, kwargs)
        marked, marked_tools, changed = mark_think_literals(messages, tools, svc.literals)
        rendered = svc.render_prompt(marked, marked_tools, kwargs)
        if changed:
            rendered, _ = unmark_think_literals(rendered, svc.literals)
        (args.private_out / (key + '.rendered.txt')).write_text(rendered)
        (args.private_out / (key + '.tokens.json')).write_text(json.dumps(ids))
        row = {'key': key, 'time': record['time'], 'request_sha256': record['body_sha256'],
               'prompt_tokens_offline': len(ids), 'rendered_sha256': sha(rendered.encode()),
               'token_ids_sha256': sha(ids), 'message_count': len(messages),
               'message_hashes': [{'role': m.get('role'), 'sha256': sha(m)} for m in messages],
               'tools_sha256': sha(tools), 'render_kwargs': kwargs,
               'previous_prompt_lcp': lcp(previous_ids, ids) if previous_ids is not None else None,
               'first_request_change': first_change(previous_req, req) if previous_req is not None else None}
        row['message_boundaries'] = [j for j, token in enumerate(ids) if token == 248045]
        rows.append(row)
        previous_ids, previous_req = ids, req
    report = {'capture': capture, 'requests': rows,
              'limits': ['Reconcile offline token counts with serving metrics.',
                         'Adjacent requests may belong to different conversations.',
                         'Only incoming prompt prefixes; generated token state is not reconstructed.',
                         'Shared UI sampling/effort overrides must be checked separately.']}
    args.summary_out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'requests': len(rows), 'capture': capture, 'summary': str(args.summary_out)}))


if __name__ == '__main__':
    main()
