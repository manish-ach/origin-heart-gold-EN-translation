#!/usr/bin/env python3
"""Build a local, read-only screenshot gallery from native renderer test evidence."""
import argparse
import html
import json
import os
from pathlib import Path


def build(report_path, output):
    report_path, output = Path(report_path).resolve(), Path(output).resolve()
    report = json.loads(report_path.read_text())
    esc = lambda value: html.escape(str(value))
    sections = []
    for case in report.get('cases', []):
        pictures = []
        for shot in case.get('screenshots', []):
            path = Path(shot['path'])
            if not path.is_absolute(): path = Path.cwd()/path
            if not path.is_file():
                raise ValueError(f'Missing screenshot: {path}')
            url = os.path.relpath(path, output.parent)
            caption = 'Following normal-size text' if shot.get('sentinel') and not case.get('ui_case') else f"Page {shot.get('page', '?')}"
            pictures.append(f'<figure><img loading="lazy" src="{esc(url)}" alt="{esc(case["ref"])} {esc(caption)}"><figcaption>{esc(caption)}</figcaption></figure>')
        if case.get('ui_case') and case.get('after_menu'):
            url = os.path.relpath(case['after_menu'], output.parent)
            pictures.append(f'<figure><img loading="lazy" src="{esc(url)}" alt="Following printer"><figcaption>Following printer, normal size</figcaption></figure>')
        sections.append(f'''<article data-search="{esc((case['ref']+' '+case.get('text','')).lower())}"><header><h2>{esc(case['ref'])}</h2><span>{esc(case['status'])}</span></header><p class="text">{esc(case.get('text',''))}</p><div class="shots">{''.join(pictures)}</div><details><summary>Recorded evidence</summary><pre>{esc(json.dumps({k:v for k,v in case.items() if k not in ('screenshots','text')},ensure_ascii=False,indent=2))}</pre></details></article>''')
    output.write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Enlarged text · Native rendering evidence</title><style>
body{margin:0;background:#eef2f6;color:#203042;font:16px/1.55 system-ui,sans-serif}main{max-width:1180px;margin:auto;padding:32px}h1{font-size:32px;margin:0}p{max-width:900px}input{font:inherit;width:min(100%,520px);box-sizing:border-box;padding:12px;border:1px solid #abb8c7;border-radius:8px;margin:10px 0 20px}article{background:white;border:1px solid #d9e0e7;border-radius:12px;padding:22px;margin:20px 0}article header{display:flex;gap:16px;align-items:center;flex-wrap:wrap}h2{margin:0;font-size:20px}header span{background:#edf2f7;border-radius:6px;padding:4px 10px;font-size:13px}.shots{display:flex;gap:20px;flex-wrap:wrap}figure{margin:12px 0}img{width:256px;max-width:100%;height:auto;image-rendering:pixelated;border:1px solid #afb9c3}figcaption{font-size:13px}.text,pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.65 ui-monospace,monospace}details{margin-top:18px}.notice{border-left:4px solid #d6a434;background:#fff9e8;padding:14px}article[hidden]{display:none}
</style><main><h1>Enlarged text, in the game renderer</h1><p>Actual emulator captures from an isolated dialogue test fixture. The production strings are shown through the native field printer. Pokéathlon cases select their native font in this fixture; max-name cases substitute seven wide letters to test geometry. This verifies that rendering context; it does not claim that every original story event was played.</p><p class="notice">Read the recorded status for each case. A screenshot alone is not proof of memory safety. Deliberately broken negative-control cases may appear here and must fail.</p><label for="search">Find a reference or phrase</label><br><input id="search" type="search" placeholder="0616#37, Misty, Gyarados…"><p id="count"></p>'''+''.join(sections)+'''</main><script>const input=document.querySelector('#search'),cards=[...document.querySelectorAll('article')];function filter(){let count=0;for(const card of cards){card.hidden=!card.dataset.search.includes(input.value.toLowerCase());if(!card.hidden)count++;}document.querySelector('#count').textContent=`${count} of ${cards.length} test cases`;}input.addEventListener('input',filter);filter();</script></html>''')
    return len(sections)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--serve',action='store_true',help='Serve only HTML and PNG evidence on loopback')
    parser.add_argument('--port',type=int,default=8767)
    args=parser.parse_args()
    print(f'{build(args.report,args.output)} cases: {args.output}')

    if args.serve:
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import unquote,urlparse
        root=args.output.resolve().parent
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*a,**kw):super().__init__(*a,directory=str(root),**kw)
            def send_head(self):
                if self.headers.get('Host') not in (f'127.0.0.1:{args.port}',f'localhost:{args.port}'):
                    self.send_error(403);return
                name=unquote(urlparse(self.path).path).lstrip('/') or args.output.name
                candidate=(root/name).resolve()
                if not candidate.is_relative_to(root) or candidate.suffix not in ('.html','.png') or not candidate.is_file():
                    self.send_error(404);return
                if not urlparse(self.path).path.strip('/'):self.path='/'+args.output.name
                return super().send_head()
            def log_message(self,*a):pass
        print(f'Gallery: http://127.0.0.1:{args.port}',flush=True)
        ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
