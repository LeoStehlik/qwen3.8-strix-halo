#!/usr/bin/env python3
"""Check capture integrity before trusting prefix evidence; no GPU or network."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('audit', Path(__file__).with_name('strata-wire-prefix-audit.py'))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def packet(seq, payload, flags=0x18):
    ip = bytearray(20)
    ip[0] = 0x45
    ip[9] = 6
    struct.pack_into('!H', ip, 2, 40 + len(payload))
    ip[12:20] = bytes([100, 99, 235, 45, 100, 96, 8, 54])
    tcp = bytearray(20)
    struct.pack_into('!HHI', tcp, 0, 55555, 8083, seq & 0xffffffff)
    tcp[12], tcp[13] = 0x50, flags
    return bytes(ip + tcp) + payload


def pcap(packets):
    out = struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 262144, 101)
    for i, p in enumerate(packets):
        out += struct.pack('<IIII', 1000 + i, 0, len(p), len(p)) + p
    return out


def request(text):
    raw = json.dumps({'model': 'public', 'messages': [{'role': 'user', 'content': text}]}).encode()
    return (b'POST /v1/chat/completions HTTP/1.1\r\nAuthorization: Bearer test-secret\r\nContent-Length: '
            + str(len(raw)).encode() + b'\r\n\r\n' + raw)


class CaptureIntegrity(unittest.TestCase):
    def parse(self, data):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'capture.pcap'
            p.write_bytes(data)
            return audit.read_requests(p)

    def test_reorder_duplicate_and_sequence_wrap(self):
        raw = request('public fixture')
        base = 2**32 - 100
        packets = [packet(base - 1, b'', 2), packet(base + 100, raw[100:]),
                   packet(base, raw[:140]), packet(base + 100, raw[100:])]
        rows, report = self.parse(pcap(packets))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['request']['messages'][0]['content'], 'public fixture')
        self.assertEqual(report['streams_with_gaps'], 0)
        self.assertNotIn('test-secret', json.dumps(rows))

    def test_gap_never_becomes_valid_prompt(self):
        raw = request('missing byte')
        rows, report = self.parse(pcap([packet(100, raw[:50]), packet(151, raw[51:])]))
        self.assertEqual(rows, [])
        self.assertEqual(report['streams_with_gaps'], 1)

    def test_conflicting_retransmission_rejected(self):
        raw = request('public')
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            self.parse(pcap([packet(100, raw), packet(100, b'X' + raw[1:])]))

    def test_keepalive_two_requests_and_incomplete_third(self):
        raw = request('one') + request('two') + request('unfinished')[:-10]
        rows, _ = self.parse(pcap([packet(100, raw)]))
        self.assertEqual([r['request']['messages'][0]['content'] for r in rows], ['one', 'two'])

    def test_capture_ending_inside_packet(self):
        one = pcap([packet(100, request('one'))])
        suffix = pcap([packet(500, request('two'))])[24:]
        rows, report = self.parse(one + suffix[:-8])
        self.assertEqual(len(rows), 1)
        self.assertTrue(report['incomplete_last_packet'])

    def test_mid_request_capture_not_guessed(self):
        rows, _ = self.parse(pcap([packet(100, request('partial')[30:])]))
        self.assertEqual(rows, [])


if __name__ == '__main__':
    unittest.main()
