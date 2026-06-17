import sys, re, json, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, 'scripts')

def parse_robust(path):
    raw = open(path, encoding='utf-8').read()
    cleaned = re.sub(r'<planung>.*?</planung>', '', raw, flags=re.DOTALL).strip()
    cleaned = re.sub(r'^```[a-z]*\n?', '', cleaned, flags=re.MULTILINE).strip().rstrip('`').strip()
    dec = json.JSONDecoder()
    try:
        obj, idx = dec.raw_decode(cleaned)
    except Exception as e:
        return None, str(e)
    # Wrapper {article, source_passages}?
    if isinstance(obj, dict) and 'article' in obj:
        return obj['article'], obj.get('source_passages', [])
    return obj, []

def show(label, path):
    art, sp = parse_robust(path)
    if art is None:
        print(f'{label}: FEHLER: {sp}')
        return
    secs  = art.get('sections', [])
    sents = [s for sec in secs for s in sec.get('sentences', [])]
    boxes = [b for sec in secs for b in sec.get('boxes', [])]  # section-level
    quiz  = art.get('quiz', {})
    imgs  = art.get('images', [])
    sp2   = art.get('source_passages', sp)
    wc    = sum(len(s.get('text', '').split()) for s in sents)
    box_wc = sum(len(b.get('text', '').split()) + len(b.get('reveal_text', '').split()) for b in boxes)

    print(f'--- {label} ---')
    print(f'sections={len(secs)}  sentences={len(sents)}  words={wc}  box_words={box_wc}  '
          f'boxes={len(boxes)}  quiz_qs={len(quiz.get("questions", []))}  images={len(imgs)}  sp={len(sp2)}')
    for sec in secs:
        role = sec.get('section_role', '?')
        h    = sec.get('heading', '')
        n    = len(sec.get('sentences', []))
        bx   = sec.get('boxes', [])
        box_info = ', '.join(b.get('type','?') for b in bx) if bx else '-'
        print(f'  [{role:25}] {repr(h)[:42]:42} {n} Saetze  boxes=[{box_info}]')
    for b in boxes:
        bt  = b.get('type', '?')
        txt = b.get('text', '')[:70]
        rev = f' -> {b["reveal_text"][:55]!r}' if b.get('reveal_text') else ''
        print(f'  BOX {bt!r:15} {repr(txt)}{rev}')
    if sents:
        print(f'  S1: {repr(sents[0].get("text","")[:110])}')
    if len(sents) > 1:
        print(f'  S2: {repr(sents[1].get("text","")[:110])}')
    qs = quiz.get('questions', [])
    if qs:
        q0 = qs[0]
        print(f'  Quiz[0]: {repr(q0.get("text","")[:80])}  correct={q0.get("correct_key")}')
    if sp2:
        print(f'  SP[0]: claim={repr(sp2[0].get("claim","")[:60])}')
    print()

show('A-MEDIUM',  'articles/test_thinking_ab/elefant_s2_medium.txt')
show('B-NOTHINK', 'articles/test_thinking_ab/elefant_s2_no_thinking.txt')
