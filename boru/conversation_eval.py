"""Opt-in, fictional dialogue evaluation. Heuristic checks are NOT a quality score."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from uuid import uuid4

from boru.assistant import AssistantService
from boru.conversation import ConversationHistory
from boru.conversation_quality import ConversationalChatModel, build_conversation_model
from boru.prompts import SystemPromptFactory


CASES = (
    {'id': 'listening', 'history': [],
     'question': 'Bugün işte çok bunaldım. Tavsiye istemiyorum, biraz içimi dökmek istiyorum.',
     'rubric': 'Duyguyu kabul et; tavsiye, başarı garantisi ve varsayım ekleme. En fazla bir doğal soru.',
     'max_words': 80, 'max_questions': 1, 'no_list': True},
    {'id': 'recall', 'history': [('Cuma günü matematik sınavım var.', 'Nasıl hissediyorsun?')],
     'question': 'Az önce hangi sınava ne zaman gireceğimi söylemiştim?',
     'rubric': 'Matematik ve cuma bilgisini doğrudan hatırla, yeni bir konu/soru ekleme.',
     'required': ['matematik', 'cuma'], 'max_questions': 0, 'max_words': 45},
    {'id': 'correction', 'history': [('Toplantım salı günü.', 'Salı gününü not ettim.'),
         ('Düzelteyim, toplantı cuma gününe alındı.', 'Tamam, cuma günü.')],
     'question': 'Toplantım hangi gündü? Yalnızca gün adını söyle.',
     'rubric': 'Güncel düzeltmeyi kullan; yalnızca Cuma yanıtı.', 'exact': 'cuma'},
    {'id': 'reference', 'history': [('Defne ile yürüyüşe çıkacağım. Ali evde kalacak.', 'İyi yürüyüşler.')],
     'question': 'Benimle yürüyüşe kim gelecekti? Sadece adını söyle.',
     'rubric': 'İki kişiyi birbirine karıştırma; yalnızca Defne yanıtı.', 'exact': 'defne'},
    {'id': 'unknown_memory', 'history': [('Biraz sohbet edelim.', 'Olur, seni dinliyorum.')],
     'question': 'Sana daha önce doğduğum şehri söylemiş miydim? Neresi olduğunu hatırlıyor musun?',
     'rubric': 'Şehir uydurma; görünür konuşmada bu bilgi olmadığını doğal biçimde belirt.',
     'forbidden': ['izmir', 'ankara', 'istanbul'], 'max_words': 70},
    {'id': 'metaphor', 'history': [],
     'question': 'Bugün beynim resmen elli sekme açık bir tarayıcı gibi. Ne demek istediğimi anladın mı? Tek cümleyle söyle.',
     'rubric': 'Zihinsel yoğunluk metaforunu anla; tarayıcı/sekme kapatma teknik desteği verme.',
     'max_words': 45, 'max_questions': 0, 'max_sentences': 1, 'no_list': True},
)


def check_answer(case, answer):
    folded = answer.casefold().replace('\u0307', '').strip()
    checks = {'nonempty': bool(folded), 'not_echo': folded != case['question'].casefold(),
              'no_internal_tags': not re.search(r'<think>|^(?:system|assistant):', folded),
              'no_failure_message': 'düzgün bir yanıt oluşturamadım' not in folded}
    if 'required' in case:
        checks['required_facts'] = all(word in folded for word in case['required'])
        checks['known_facts_not_denied'] = re.search(r'ulaşamadım|bulamadım|hatırlamıyorum|bilmiyorum|belirtmedin|söylemedin|paylaşmadın', folded) is None
    if 'forbidden' in case:
        checks['no_listed_inventions'] = not any(word in folded for word in case['forbidden'])
    if 'exact' in case:
        checks['exact_answer'] = re.sub(r'[^\w]', '', folded) == case['exact']
    if 'max_words' in case:
        checks['length'] = len(answer.split()) <= case['max_words']
    if 'max_questions' in case:
        checks['questions'] = answer.count('?') <= case['max_questions']
    if case.get('no_list'):
        checks['not_a_list'] = re.search(r'^\s*(?:[-*]|\d+[.)])\s', answer, re.M) is None
    if 'max_sentences' in case:
        checks['sentences'] = len([s for s in re.split(r'[.!?]+', answer) if s.strip()]) <= case['max_sentences']
    return checks


def evaluate(model_name, *, limit=6, model=None):
    # No user profile, repository, network search or tool execution in this benchmark.
    owned = model is None
    model = model or build_conversation_model(model_name, timeout=60)
    try:
        return _evaluate_cases(model_name, model, limit)
    finally:
        if owned:
            model.close()


def _evaluate_cases(model_name, model, limit):
    rows = []
    for case in CASES[:limit]:
        history = ConversationHistory(max_turns=5)
        for user, assistant in case['history']:
            history.add_turn(user, assistant)
        assistant = AssistantService(ConversationalChatModel(model), history,
                                     SystemPromptFactory(conversational=True))
        started = monotonic()
        try:
            answer = assistant.reply(case['question'])
            checks = check_answer(case, answer)
            row = {'case': case['id'], 'answer': answer, 'checks': checks,
                   'status': 'checks_passed' if all(checks.values()) else 'check_failed'}
        except Exception as error:
            row = {'case': case['id'], 'answer': '', 'checks': {},
                   'status': 'error', 'error_type': type(error).__name__}
        row.update(seconds=round(monotonic() - started, 3), rubric=case['rubric'],
                   question=case['question'], history=case['history'], human_review='not_rated')
        rows.append(row)
        print(json.dumps({'model': model_name, **row}, ensure_ascii=True), flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', required=True, help='Installed local models, comma separated')
    parser.add_argument('--label', default='dialogue')
    parser.add_argument('--limit', type=int, choices=range(1, len(CASES) + 1), default=6)
    args = parser.parse_args()
    names = list(dict.fromkeys(name.strip() for name in args.models.split(',') if name.strip()))
    if not 1 <= len(names) <= 3:
        parser.error('Bir ila üç kurulu model belirtin.')
    report = {'label': args.label, 'created_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Synthetic isolated chat core; heuristic checks are not semantic quality ratings.',
              'prompt': SystemPromptFactory(conversational=True).build(), 'results': {}}
    report['generation_profile'] = {'temperature': 0.35, 'num_predict': 1024,
                                    'qwen3_think': False, 'timeout': 60, 'max_attempts': 2}
    for name in names:
        report['results'][name] = evaluate(name, limit=args.limit)
    root = Path(__file__).resolve().parents[1] / 'data' / 'conversation_evals'
    root.mkdir(parents=True, exist_ok=True)
    path = root / (uuid4().hex + '.json')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print('REPORT=' + str(path), flush=True)


if __name__ == '__main__':
    main()
