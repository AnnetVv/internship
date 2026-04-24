# Імпорт бібліотек
import textgrid
import re
from pathlib import Path
from typing import List, Dict


# Валідатор з перевірками
class TextGridValidator:

# Очікувані рівні (tiers) у файлі TextGrid
    EXPECTED_TIERS = ['SPK-A-text', 'SPK-A-emo', 'SPK-B-text', 'SPK-B-emo', 'clap-sync']
# Список допустимих емоцій
    VALID_EMOTIONS = {
        'j1', 'j2', 'j3', 'sad1', 'sad2', 'sad3', 'an1', 'an2', 'an3', 'f1', 'f2', 'f3',
        'nsur1', 'nsur2', 'nsur3', 'psur1', 'psur2', 'psur3', 'dis1', 'dis2', 'dis3',
        'con1', 'con2', 'con3', 'ad1', 'ad2', 'ad3', 'o', 'n'
    }

# Емоції, які мають містити інтенсивність (цифру 1–3)
    EMOTIONS_WITH_INTENSITY = {'j', 'sad', 'an', 'f', 'nsur', 'psur', 'dis', 'con', 'ad'}
# Емоції, які НЕ повинні містити цифру
    EMOTIONS_WITHOUT_INTENSITY = {'o', 'n'}

# Допустимі маркери в зірочках (*...*)
    VALID_STAR_MARKS = {
        'у', 'р', 'р-укр', 'р-ак', 'англ', 'нім', 'фр', 'с', 'ін',
        'о', 'об', 'роз', 'пскл', 'пбкв', 'з', 'шеп', 'гарк', 'зклдн', 'клуб',
        'шт', 'см', 'сміх', 'плач', 'зітх', 'к', 'кд', 'вд', 'івд', 'пл', 'шм',
        'е', 'угу', 'позіх', 'хм', 'гкхм', 'пф', 'у-у', 'м', 'сьорб', 'св', 'ковт',
        'м-м', 'ммм', 'м-мм', 'ааа', 'мммм', 'ім', 'йой', 'виг', 'цьом', 'плю',
        'хлип', 'цок', 'чих', 'насп', 'відриг', 'гик', 'пос', 'крк', 'тч', 'спів',
        'шепіт', 'усвід', 'розч', 'сарк', 'хв', 'посл'
    }

    def __init__(self):
        # Список для накопичення знайдених помилок
        self.errors = []

# Валідація одного файлу
    def validate_file(self, filepath: Path) -> List[Dict]:
        self.errors = []

# Спроба відкрити та зчитати файл TextGrid
        try:
            tg = textgrid.TextGrid.fromFile(str(filepath))
        except Exception as e:
# Якщо файл не читається — додаємо помилку і завершуємо перевірку
            self.errors.append({'file': filepath.name, 'check': 'READ_ERROR', 'msg': str(e)})
            return self.errors
# Перевірка кількості рівнів (tiers)
        if len(tg.tiers) != 5:
            self.errors.append({'file': filepath.name, 'check': '9_TIER_COUNT',
                                'msg': f'Очікується 5 рівнів, знайдено {len(tg.tiers)}'})
            return self.errors
# Перевірка назв кожного рівня
        for i, tier in enumerate(tg.tiers):
            if tier.name not in self.EXPECTED_TIERS:
                self.errors.append({'file': filepath.name, 'check': '4_TIER_NAME',
                                    'msg': f'Рівень {i}: "{tier.name}" - очікується {self.EXPECTED_TIERS}'})
# Формуємо словник потрібних tiers
        tiers = {tier.name: tier for tier in tg.tiers if tier.name in self.EXPECTED_TIERS}
        if len(tiers) != 5:
            return self.errors
# Перевірки для кожного мовця
        for spk in ['SPK-A', 'SPK-B']:
            text_tier = tiers[f'{spk}-text']    # текстовий рівень
            emo_tier = tiers[f'{spk}-emo']       # рівень емоцій

# Перевірка: перша репліка має починатися з *у*
            if len(text_tier) > 0:
                first_text = text_tier[0].mark.strip() if text_tier[0].mark else ''
                if first_text and not first_text.startswith('*у*'):
                    self.errors.append({'file': filepath.name, 'check': '13_FIRST_UTTERANCE_NO_STAR_U',
                                        'msg': f'{spk}: перша репліка не починається з *у*. Початок: "{first_text[:50]}"',
                                        'time': f'{text_tier[0].minTime:.3f}-{text_tier[0].maxTime:.3f}'})

# Перевірка кожного інтервалу (синхронно текст + емоція)
            for i, (t_int, e_int) in enumerate(zip(text_tier, emo_tier)):
                # Перевірка синхронізації початку
                if abs(t_int.minTime - e_int.minTime) > 0.001:
                    self.errors.append({'file': filepath.name, 'check': '3_BOUNDARY',
                                        'msg': f'{spk} інт.{i + 1}: початок не збігається ({t_int.minTime:.3f} vs {e_int.minTime:.3f})',
                                        'time': f'{t_int.minTime:.3f}-{t_int.maxTime:.3f}'})
                # Перевірка синхронізації кінця
                if abs(t_int.maxTime - e_int.maxTime) > 0.001:
                    self.errors.append({'file': filepath.name, 'check': '3_BOUNDARY',
                                        'msg': f'{spk} інт.{i + 1}: кінець не збігається ({t_int.maxTime:.3f} vs {e_int.maxTime:.3f})',
                                        'time': f'{t_int.minTime:.3f}-{t_int.maxTime:.3f}'})
                # Очищення тексту від пробілів
                t_text = t_int.mark.strip() if t_int.mark else ''
                e_text = e_int.mark.strip() if e_int.mark else ''
                # Є текст, але немає емоції
                if t_text and not e_text:
                    self.errors.append({'file': filepath.name, 'check': '6_EMPTY_EMOTION',
                                        'msg': f'{spk} інт.{i + 1}: є текст "{t_text[:30]}", але емоція порожня',
                                        'time': f'{t_int.minTime:.3f}-{t_int.maxTime:.3f}'})
                # Є емоція, але немає тексту
                if not t_text and e_text:
                    self.errors.append({'file': filepath.name, 'check': '6_ORPHAN_EMOTION',
                                        'msg': f'{spk} інт.{i + 1}: текст порожній, але є емоція "{e_text}"',
                                        'time': f'{t_int.minTime:.3f}-{t_int.maxTime:.3f}'})

                # Детальні перевірки
                if t_text:
                    self._check_text(t_text, spk, i + 1, t_int, filepath.name)
                if e_text:
                    self._check_emotion(e_text, spk, i + 1, e_int, filepath.name)

# Перевірка clap-tier (має бути рівно один clap)
        clap_tier = tiers.get('clap-sync')
        if clap_tier:
            claps = [i for i in clap_tier if i.mark and i.mark.strip()]
            if len(claps) == 0:
                self.errors.append({'file': filepath.name, 'check': '8_CLAP_MISSING', 'msg': 'Немає мітки clap'})
            elif len(claps) > 1:
                self.errors.append({'file': filepath.name, 'check': '8_CLAP_MULTIPLE',
                                    'msg': f'Знайдено {len(claps)} міток clap (має бути 1)'})
            elif claps[0].mark.strip().lower() != 'clap':
                self.errors.append({'file': filepath.name, 'check': '8_CLAP_WRONG',
                                    'msg': f'Мітка має бути "clap", знайдено "{claps[0].mark}"'})

        # Додаткові перевірки: текст в emo і емоція в text
        for spk in ['SPK-A', 'SPK-B']:
            for interval in tiers[f'{spk}-emo']:
                mark = interval.mark.strip() if interval.mark else ''
                if mark and len(mark) > 4 and re.search(r'[а-яієїґ]', mark.lower()):
                    self.errors.append({'file': filepath.name, 'check': '10_TEXT_IN_EMO',
                                        'msg': f'{spk}: текст "{mark}" в рівні емоцій',
                                        'time': f'{interval.minTime:.3f}-{interval.maxTime:.3f}'})

            for interval in tiers[f'{spk}-text']:
                mark = interval.mark.strip() if interval.mark else ''
                if mark and mark in self.VALID_EMOTIONS:
                    self.errors.append({'file': filepath.name, 'check': '10_EMO_IN_TEXT',
                                        'msg': f'{spk}: емоція "{mark}" в рівні тексту',
                                        'time': f'{interval.minTime:.3f}-{interval.maxTime:.3f}'})

        return self.errors

# Перевірки тексту
    def _check_text(self, text: str, spk: str, idx: int, interval, filename: str):
        # Перевірка пробілу на початку
        if text.startswith(' '):
            self.errors.append({'file': filename, 'check': '11_LEADING_SPACE',
                                'msg': f'{spk} інт.{idx}: текст починається з пробілу: "{text[:30]}"',
                                'time': f'{interval.minTime:.3f}-{interval.maxTime:.3f}'})
        # Перевірка пробілу в кінці
        if text.endswith(' '):
            self.errors.append({'file': filename, 'check': '11_TRAILING_SPACE',
                                'msg': f'{spk} інт.{idx}: текст закінчується пробілом: "...{text[-30:]}"',
                                'time': f'{interval.minTime:.3f}-{interval.maxTime:.3f}'})
        # Перевірка подвійних пробілів
        if '  ' in text:
            self.errors.append({'file': filename, 'check': '12_DOUBLE_SPACE',
                                'msg': f'{spk} інт.{idx}: знайдено подвійні пробіли: "{text[:50]}"',
                                'time': f'{interval.minTime:.3f}-{interval.maxTime:.3f}'})
        # Перевірки форматування *...*
        for mark in self.VALID_STAR_MARKS:
            pattern_merge_left = rf'[^ ]\*{re.escape(mark)}\*'
            for m in re.finditer(pattern_merge_left, text):
                self.errors.append({'file': filename, 'check': '1_STAR_MERGE_LEFT',
                                    'msg': f'{spk} інт.{idx}: зірочки зливаються зліва: "...{text[max(0, m.start()):m.end()]}..." (має бути пробіл перед *{mark}*)',
                                    'time': f'{interval.minTime:.3f}-{interval.maxTime:.3f}'})
                break

            pattern_merge_right = rf'\*{re.escape(mark)}\*[^ ]'
            for m in re.finditer(pattern_merge_right, text):
                self.errors.append({'file': filename, 'check': '1_STAR_MERGE_RIGHT',
                                    'msg': f'{spk} інт.{idx}: зірочки зливаються справа: "...{text[m.start():min(m.end() + 5, len(text))]}..." (має бути пробіл після *{mark}*)',
                                    'time': f'{interval.minTime:.3f}-{interval.maxTime:.3f}'})
                break

        for mark in self.VALID_STAR_MARKS:
            patterns = [
                (rf'\* {re.escape(mark)}\*', f'* {mark}*'),
                (rf'\*{re.escape(mark)} \*', f'*{mark} *'),
                (rf'\* {re.escape(mark)} \*', f'* {mark} *')
            ]
            for pattern, wrong_format in patterns:
                for m in re.finditer(pattern, text):
                    self.errors.append({'file': filename, 'check': '2_STAR_INTERNAL_SPACE',
                                        'msg': f'{spk} інт.{idx}: пробіл всередині зірочок: "{m.group(0)}" (має бути без пробілів, наприклад: *{mark}*)',
                                        'time': f'{interval.minTime:.3f}-{interval.maxTime:.3f}'})
                    break

# Перевірки емоцій
    def _check_emotion(self, emotion: str, spk: str, idx: int, interval, filename: str):
        emo_low = emotion.lower()
        # Перевірка валідності
        if emo_low not in self.VALID_EMOTIONS:
            self.errors.append({'file': filename, 'check': '5_INVALID_EMOTION',
                                'msg': f'{spk} інт.{idx}: недозволена емоція "{emotion}"',
                                'time': f'{interval.minTime:.3f}-{interval.maxTime:.3f}'})
            return

        # Перевірка інтенсивності
        base = re.sub(r'[0-9]', '', emo_low)
        has_digit = bool(re.search(r'[0-9]', emo_low))

        if base in self.EMOTIONS_WITH_INTENSITY and not has_digit:
            self.errors.append({'file': filename, 'check': '7_MISSING_INTENSITY',
                                'msg': f'{spk} інт.{idx}: "{emotion}" має мати цифру 1-3',
                                'time': f'{interval.minTime:.3f}-{interval.maxTime:.3f}'})
        elif base in self.EMOTIONS_WITHOUT_INTENSITY and has_digit:
            self.errors.append({'file': filename, 'check': '7_UNEXPECTED_INTENSITY',
                                'msg': f'{spk} інт.{idx}: "{emotion}" не має мати цифру',
                                'time': f'{interval.minTime:.3f}-{interval.maxTime:.3f}'})

# Знаходить всі файли анотацій у структурі папок
def find_annotation_files(base_path: Path) -> List[Path]:
    files = []
    lines = []
    lines.append(f"\nПошук у: {base_path}") # Інформацію про шлях пошуку

    # Шаблони пошуку файлів
    patterns = [
        "DLG*/audio/MIC3/*.TextGrid",
        "DLG*/audio/MIC1/*_synced.TextGrid",
        "DLG*/audio/MIC2/*_synced.TextGrid",
        "DLG*/sync/*.TextGrid",
    ]

    # Пошук файлів за кожним шаблоном
    for pattern in patterns:
        found_files = list(base_path.glob(pattern))
        files.extend(found_files)
        if found_files:
            lines.append(f"\nЗнайдено {len(found_files)} файлів за шаблоном: {pattern}")
            for f in found_files:
                try:
                    rel_path = f.relative_to(base_path)
                    lines.append(f"  - {rel_path}")
                except:
                    lines.append(f"  - {f}")

    return files, lines


def main():
    base_path = Path("/Users/macbook/Documents/практика")  # Шлях до папки з даними
    output_file = Path("/Users/macbook/Documents/практика/script.txt")

    lines = []
    lines.append("=" * 70)
    lines.append("ПЕРЕВІРКА ФАЙЛІВ АНОТАЦІЙ")
    lines.append(f"Шлях: {base_path}")

    if not base_path.exists():
        lines.append(f"Шлях не існує: {base_path}")
    else:
        files, search_lines = find_annotation_files(base_path)
        lines.extend(search_lines)

        if not files:
            lines.append(f'\nФайлів TextGrid не знайдено')
        else:
            lines.append(f"\nЗнайдено {len(files)} файлів для перевірки")

            validator = TextGridValidator()
            all_errors = []
            files_with_errors = set()
            error_count_by_file = {}

            for f in files:
                errors = validator.validate_file(f)
                all_errors.extend(errors)
                if errors:
                    files_with_errors.add(f.name)
                    error_count_by_file[f.name] = len(errors)
                    lines.append(f'\n{"=" * 70}')
                    lines.append(f' {f.name}')
                    lines.append(f'{"=" * 70}')
                    errors_by_type = {}

                    for err in errors:
                        check_type = err["check"]
                        if check_type not in errors_by_type:
                            errors_by_type[check_type] = []
                        errors_by_type[check_type].append(err)

                    for check_type, errs in errors_by_type.items():
                        lines.append(f"\n   {check_type}:")
                        for err in errs:
                            time_str = f" [{err.get('time', '')}]" if err.get('time') else ''
                            lines.append(f"     • {err['msg']}{time_str}")
                else:
                    lines.append(f'\n {f.name} - помилок не знайдено')

            lines.append(f'\n{"=" * 70}')
            lines.append(f' ПІДСУМОК')
            lines.append(f'Перевірено файлів: {len(files)}')
            lines.append(f'Знайдено помилок: {len(all_errors)}')
            lines.append(f'Файлів з помилками: {len(files_with_errors)}')

            if files_with_errors:
                lines.append(f'\n Список файлів з помилками:')
                for fname in sorted(files_with_errors):
                    lines.append(f'  - {fname} ({error_count_by_file[fname]} помилок)')

                lines.append(f'\n СТАТИСТИКА ПОМИЛОК ЗА ТИПАМИ:')
                errors_by_type_total = {}
                for err in all_errors:
                    check_type = err["check"]
                    if check_type not in errors_by_type_total:
                        errors_by_type_total[check_type] = 0
                    errors_by_type_total[check_type] += 1

                for check_type, count in sorted(errors_by_type_total.items()):
                    lines.append(f'  {check_type}: {count} помилок')

    lines.append("=" * 70)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"Звіт збережено у файл: {output_file}")


if __name__ == '__main__':
    main()  
