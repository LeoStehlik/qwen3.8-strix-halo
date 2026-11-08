#!/usr/bin/env python3
"""Offline reproduction of compact-tool/undeclared-name failures; no inference.

Uses the installed Strata parser with public minimal schemas and the failed XML
forms. Executes no tools, reads no session transcript and changes no services.
"""
import argparse
import json
from pathlib import Path
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--terminal', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    sys.path.insert(0, str(a.terminal))
    from serve.frontend import OutputParser
    compact = [{'name': 'tool_call', 'parameters': {'type': 'object', 'required': ['id'],
                'properties': {'id': {'type': 'string'}, 'args': {'type': 'object'}}}}]
    search = {'name': 'skills_search', 'parameters': {'type': 'object', 'required': ['query'],
              'properties': {'query': {'type': 'string'}, 'limit': {'type': 'integer'}}}}
    read = {'name': 'skills_read', 'parameters': {'type': 'object', 'required': ['name'],
            'properties': {'name': {'type': 'string'}}}}

    def xml(name, args):
        body = ''.join(f'<parameter={k}>\n{v if isinstance(v, str) else json.dumps(v)}\n</parameter>\n'
                       for k, v in args.items())
        return f'<tool_call>\n<function={name}>\n{body}</function>\n</tool_call>'

    failed_search = xml('skills_search', {'query': 'no-slop-ui frontend design review'})
    failed_read = xml('skills_read', {'skillName': 'no-slop-ui'})
    cases = [
        ('undeclared_search', compact, failed_search, False, None),
        ('undeclared_read', compact, failed_read, False, None),
        ('declared_search', compact + [search, read], failed_search, True, {'query': 'no-slop-ui frontend design review'}),
        ('declared_read_still_wrong_argument', compact + [search, read], failed_read, True, {'skillName': 'no-slop-ui'}),
        ('correct_wrapped_read', compact, xml('tool_call', {'id': 'skills_read', 'args': {'name': 'no-slop-ui'}}),
         True, {'id': 'skills_read', 'args': {'name': 'no-slop-ui'}}),
        ('correct_direct_read_when_declared', compact + [search, read], xml('skills_read', {'name': 'no-slop-ui'}),
         True, {'name': 'no-slop-ui'})]
    report = {'protocol': 'compact-tool-surface-repro-v1', 'inference_requests': 0, 'tools_executed': 0, 'cases': []}
    for name, tools, raw, accepted, expected_args in cases:
        checks = []
        for chunk in (1, 7, len(raw)):
            for stream in (False, True):
                parser = OutputParser(thinking=False, tools=tools, recover=True, declared_only=True, stream_tools=stream)
                events = []
                for pos in range(0, len(raw), chunk):
                    events.extend(parser.feed(raw[pos:pos + chunk]))
                events.extend(parser.finish())
                calls = [e.call for e in events if e.kind == 'tool_call']
                content = ''.join(e.text for e in events if e.kind == 'content')
                assert len(calls) == int(accepted), name
                if accepted:
                    assert calls[0].arguments == expected_args and not content, name
                else:
                    assert content == raw and parser.unread_names, name
                checks.append({'chunk': chunk, 'stream_tools': stream, 'calls': len(calls),
                               'rejected_names': parser.unread_names, 'passed': True})
        report['cases'].append({'case': name, 'checks': checks,
            'argument_contract_valid': name != 'declared_read_still_wrong_argument' if accepted else None})
    report['passed'] = True
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, 'parser_checks': sum(len(c['checks']) for c in report['cases']),
                      'inference_requests': 0, 'tools_executed': 0}))


if __name__ == '__main__':
    main()
