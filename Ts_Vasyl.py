import numpy as np  # бібліотека для роботи з масивами і числовими операціями
import soundfile as sf  # бібліотека для читання аудіофайлів
import librosa  # бібліотека для аудіоаналізу та покращення
from pathlib import Path  # робота з файловою системою
import re  # регулярні вирази
import warnings  # для роботи з попередженнями

warnings.filterwarnings('ignore')

# Імпорт з pyannote для роботи з сегментами та оцінкою якості
from pyannote.core import Segment, Annotation
from pyannote.metrics.detection import DetectionErrorRate


# Функція для покращення аудіо за допомогою librosa
def enhance_audio_with_librosa(audio, sr):
    # 1. Спектральне шумозаглушення
    try:
        # Перетворюємо сигнал у спектр (STFT)
        D = librosa.stft(audio)
        magnitude = np.abs(D)  # амплітуда
        phase = np.angle(D)  # фаза

        # Беремо перші 0.3 секунди як шум
        noise_frames = max(1, int(0.3 * sr / 512))
        noise_profile = np.mean(magnitude[:, :noise_frames], axis=1, keepdims=True)

        # Віднімаємо шум
        magnitude_clean = magnitude - noise_profile * 0.3
        magnitude_clean = np.maximum(magnitude_clean, 0)  # не допускаємо від'ємних значень

        # Відновлюємо сигнал
        D_clean = magnitude_clean * np.exp(1j * phase)
        audio_clean = librosa.istft(D_clean)

        # Обрізаємо якщо стало довше
        if len(audio_clean) > len(audio):
            audio_clean = audio_clean[:len(audio)]

    except:
        audio_clean = audio.copy()

    # 2. Нормалізація гучності
    rms = np.sqrt(np.mean(audio_clean ** 2)) # середня енергія сигналу
    if rms > 0:
        target_rms = 0.1 # бажаний рівень гучності
        audio_normalized = audio_clean * (target_rms / rms)
    else:
        audio_normalized = audio_clean

    # обмежуємо значення
    audio_normalized = np.clip(audio_normalized, -1, 1)

    return audio_normalized


# СИСТЕМА 1: TEN_VAD
class TEN_VAD:

    def __init__(self, threshold=0.005, frame_ms=15, sample_rate=16000, boost_factor=10, use_librosa_enhancement=True):
        self.threshold = threshold  # поріг для визначення мовлення
        self.frame_ms = frame_ms  # довжина фрейму
        self.sample_rate = sample_rate
        self.frame_samples = int(sample_rate * frame_ms / 1000)  # розмір фрейму в семплах
        self.boost_factor = boost_factor  # підсилення сигналу
        self.use_librosa_enhancement = use_librosa_enhancement

    def preprocess_audio(self, audio):   # Покращення аудіо
        if self.use_librosa_enhancement:
            audio = enhance_audio_with_librosa(audio, self.sample_rate)

        # Нормалізація
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = audio / max_val

        # Підсилення
        audio = audio * self.boost_factor

        # Обрізка значень
        audio = np.clip(audio, -1, 1)

        return audio

    def process_audio(self, audio):
        # Попередня обробка
        audio = self.preprocess_audio(audio)
        energies = []

        # Розбиваємо сигнал на фрейми і рахуємо енергію
        for i in range(0, len(audio) - self.frame_samples, self.frame_samples):
            frame = audio[i:i + self.frame_samples]
            energy = np.mean(frame ** 2)
            energies.append(energy)

        if not energies:
            return [], []

        energies = np.array(energies)
        max_energy = np.max(energies)

        # Нормалізуємо енергію (0–1)
        if max_energy > 0:
            scores = energies / max_energy
        else:
            scores = energies

        labels = [1 if s > self.threshold else 0 for s in scores]

        return scores.tolist(), labels

    def get_segments(self, labels, scores, audio_duration):
        segments = []
        in_speech = False  # чи зараз у мовленні
        start_frame = 0
        frame_duration = self.frame_ms / 1000.0  # тривалість фрейму в секундах

        for i, label in enumerate(labels):
            # Початок мовлення
            if label == 1 and not in_speech:
                start_frame = i
                in_speech = True
                # Кінець мовлення
            elif label == 0 and in_speech:
                start_time = start_frame * frame_duration
                end_time = i * frame_duration
                if end_time - start_time >= 0.05:
                    segment_scores = scores[start_frame:i]
                    # середній "рівень впевненості"
                    voice_score = np.mean(segment_scores) if segment_scores else 0.5
                    segments.append({
                        'start': round(start_time, 3),
                        'end': round(end_time, 3),
                        'voice_score': round(voice_score, 3)
                    })
                in_speech = False

        # Якщо мовлення закінчилось разом із аудіо
        if in_speech:
            start_time = start_frame * frame_duration
            end_time = len(labels) * frame_duration
            if end_time - start_time >= 0.05:
                segment_scores = scores[start_frame:]
                voice_score = np.mean(segment_scores) if segment_scores else 0.5
                segments.append({
                    'start': round(start_time, 3),
                    'end': round(end_time, 3),
                    'voice_score': round(voice_score, 3)
                })

        return segments


# СИСТЕМА 2: WebRTC_VAD
class WebRTC_VAD:

    def __init__(self, frame_ms=15, sample_rate=16000, use_librosa_enhancement=True):
        self.frame_ms = frame_ms
        self.sample_rate = sample_rate
        self.frame_samples = int(sample_rate * frame_ms / 1000)
        self.use_librosa_enhancement = use_librosa_enhancement

    def preprocess_audio(self, audio):
        if self.use_librosa_enhancement:
            audio = enhance_audio_with_librosa(audio, self.sample_rate)
        return audio

    def compute_adaptive_threshold(self, energies):
        #  Обчислює адаптивний поріг на основі статистики сигналу
        energies = np.array(energies)
        # логарифмічна шкала
        log_energies = np.log10(energies + 1e-10)

        # медіана
        median = np.median(log_energies)

        # MAD (median absolute deviation)
        mad = np.median(np.abs(log_energies - median))

        # адаптивний поріг
        threshold_log = median + 1.2 * mad
        threshold = 10 ** threshold_log

        return threshold

    def median_filter(self, labels, window_size=3):
        # Згладжування
        filtered = np.array(labels)
        half = window_size // 2
        for i in range(half, len(labels) - half):
            window = labels[i - half:i + half + 1]
            filtered[i] = 1 if np.sum(window) > half else 0
        return filtered.tolist()

    def apply_hangover(self, labels, hangover_frames=4):
        #  Розширює сегменти мовлення
        result = labels.copy()
        for i in range(len(labels)):
            if labels[i] == 1:
                for j in range(1, hangover_frames + 1):
                    # вперед
                    if i + j < len(labels):
                        result[i + j] = 1
                        # назад
                    if i - j >= 0:
                        result[i - j] = 1
        return result

    def process_audio(self, audio):
        audio = self.preprocess_audio(audio)

        energies = []
        # рахуємо енергію
        for i in range(0, len(audio) - self.frame_samples, self.frame_samples):
            frame = audio[i:i + self.frame_samples]
            energy = np.mean(frame ** 2)
            energies.append(energy)

        if not energies:
            return [], []

        # адаптивний поріг
        threshold = self.compute_adaptive_threshold(energies)
        # первинна класифікація
        raw_labels = [1 if e > threshold else 0 for e in energies]

        # згладжування
        filtered_labels = self.median_filter(raw_labels, window_size=3)

        # "розтягування" мовлення
        final_labels = self.apply_hangover(filtered_labels, hangover_frames=4)

        # нормалізовані оцінки
        max_energy = np.max(energies) if np.max(energies) > 0 else 1
        scores = (energies / max_energy).tolist()

        return scores, final_labels


    def get_segments(self, labels, scores, audio_duration):
        #  Формування сегментів мовлення
        segments = []
        in_speech = False
        start_frame = 0
        frame_duration = self.frame_ms / 1000.0

        for i, label in enumerate(labels):
            # початок мовлення
            if label == 1 and not in_speech:
                start_frame = i
                in_speech = True

            # кінець мовлення
            elif label == 0 and in_speech:
                start_time = start_frame * frame_duration
                end_time = i * frame_duration

                # відкидаємо дуже короткі сегменти
                if end_time - start_time >= 0.05:
                    segment_scores = scores[start_frame:i]

                    # середня впевненість
                    voice_score = np.mean(segment_scores) if segment_scores else 0.5

                    segments.append({
                        'start': round(start_time, 3),
                        'end': round(end_time, 3),
                        'voice_score': round(voice_score, 3)
                    })

                in_speech = False


        # якщо мовлення триває до кінця
        if in_speech:
            start_time = start_frame * frame_duration
            end_time = len(labels) * frame_duration

            if end_time - start_time >= 0.05:
                segment_scores = scores[start_frame:]
                voice_score = np.mean(segment_scores) if segment_scores else 0.5

                segments.append({
                    'start': round(start_time, 3),
                    'end': round(end_time, 3),
                    'voice_score': round(voice_score, 3)
                })

        return segments


# ФУНКЦІЯ ДЛЯ РОЗРАХУНКУ DER, MISS, FA
def calculate_der_components(ref, hyp, collar=0.25, total_duration=None):
    metric = DetectionErrorRate(collar=collar)
    der = metric(ref, hyp)

    # Отримуємо детальну інформацію
    details = metric.compute_components(ref, hyp)

    # Отримуємо загальну тривалість референсу
    if total_duration is None:
        total_duration = 0
        for segment, _ in ref.itertracks():
            total_duration += segment.end - segment.start

    # Якщо total_duration = 0, використовуємо 1 щоб уникнути ділення на 0
    if total_duration == 0:
        total_duration = 1

    # Перетворюємо секунди у відсотки
    miss_seconds = details.get('miss', 0)
    fa_seconds = details.get('false alarm', 0)

    miss_percent = (miss_seconds / total_duration) * 100
    fa_percent = (fa_seconds / total_duration) * 100

    return der * 100, miss_percent, fa_percent


# ФУНКЦІЇ ДЛЯ ЗБЕРЕЖЕННЯ В TXT
def save_segments_to_txt(segments, system_name, output_path):
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"{system_name}\n")
        f.write(f"{'Сегменти':<25} {'Voice Score':<15}\n")
        for seg in segments:
            f.write(f"{seg['start']:.2f}-{seg['end']:.2f}{'':<15} {seg['voice_score']:.3f}\n")
        f.write(f"Всього сегментів: {len(segments)}\n")


def save_vad_output_to_txt(scores, labels, system_name, output_path):
    # Зберігає покадровий результат VAD
    with open(output_path, 'w', encoding='utf-8') as f:
        for frame_idx, (score, label) in enumerate(zip(scores, labels)):
            f.write(f"[{frame_idx}] {score:.6f}, {label}\n")


def save_summary_table(all_results, output_path):
    # Зберігає покадровий результат VAD
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("ПІДСУМКОВЕ ОЦІНЮВАННЯ РЕЗУЛЬТАТІВ ДІАРИЗАЦІЇ ДЛЯ ВСІХ ФОНОГРАМ\n")
        f.write("=" * 80 + "\n\n")

        # розділення по системах
        ten_der = [r['der_percent'] for r in all_results if r['vad_name'] == 'TEN_VAD']
        ten_miss = [r['miss_percent'] for r in all_results if r['vad_name'] == 'TEN_VAD']
        ten_fa = [r['fa_percent'] for r in all_results if r['vad_name'] == 'TEN_VAD']

        webrtc_der = [r['der_percent'] for r in all_results if r['vad_name'] == 'WebRTC_VAD']
        webrtc_miss = [r['miss_percent'] for r in all_results if r['vad_name'] == 'WebRTC_VAD']
        webrtc_fa = [r['fa_percent'] for r in all_results if r['vad_name'] == 'WebRTC_VAD']

        # середні значення
        avg_ten_der = np.mean(ten_der) if ten_der else 0
        avg_ten_miss = np.mean(ten_miss) if ten_miss else 0
        avg_ten_fa = np.mean(ten_fa) if ten_fa else 0

        avg_webrtc_der = np.mean(webrtc_der) if webrtc_der else 0
        avg_webrtc_miss = np.mean(webrtc_miss) if webrtc_miss else 0
        avg_webrtc_fa = np.mean(webrtc_fa) if webrtc_fa else 0

        # вивід таблиці
        f.write(f"{'':<20} {'TEN_VAD':<15} {'WebRTC_VAD':<15}\n")
        f.write("-" * 50 + "\n")
        f.write(f"{'DER':<20} {avg_ten_der:>5.1f}%{'':<8} {avg_webrtc_der:>5.1f}%\n")
        f.write(f"{'MISS':<20} {avg_ten_miss:>5.1f}%{'':<8} {avg_webrtc_miss:>5.1f}%\n")
        f.write(f"{'FA':<20} {avg_ten_fa:>5.1f}%{'':<8} {avg_webrtc_fa:>5.1f}%\n\n")

        f.write(f"{'Діалог (MIC, дубль)':<25} {'TEN_VAD DER':<18} {'WebRTC_VAD DER':<18}\n")
        f.write("-" * 65 + "\n")

        grouped = {}
        for r in all_results:
            key = f"{r['dialog']} (MIC{r['mic']}, {r['take']})"
            if key not in grouped:
                grouped[key] = {}
            grouped[key][r['vad_name']] = r['der_percent']

        for key in sorted(grouped.keys()):
            ten_val = grouped[key].get('TEN_VAD', 0)
            webrtc_val = grouped[key].get('WebRTC_VAD', 0)
            f.write(f"{key:<25} {ten_val:>5.1f}%{'':<10} {webrtc_val:>5.1f}%\n")


# ПАРСИНГ TEXTGRID
def parse_reference_textgrid(file_path):
    annotation = Annotation()

    content = None
    for encoding in ['utf-8', 'utf-16', 'latin1', 'cp1252']:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            break
        except:
            continue

    if content is None:
        return annotation

    # Регулярний вираз для витягування сегментів (час початку, кінця і текст)
    pattern = r'xmin\s*=\s*([\d.]+).*?xmax\s*=\s*([\d.]+).*?text\s*=\s*"([^"]*)"'
    matches = re.findall(pattern, content, re.DOTALL)

    # Проходимо по всіх знайдених сегментах
    for xmin_str, xmax_str, text in matches:
        try:
            start = float(xmin_str)  # початок сегмента
            end = float(xmax_str)  # кінець сегмента
            text_clean = text.strip()  # очищаємо текст

            # Фільтрація: залишаємо тільки реальне мовлення
            if text_clean:
                # відкидаємо паузи/тишину
                if text_clean not in ['...', 'sil', 'SIL', 'silence', 'sp', 'pause']:
                    # відкидаємо "сміттєві" символи
                    if not re.match(r'^[\*\_\s\.\,\!\?]+$', text_clean):
                        # залишаємо тільки сегменти довші за 50 мс
                        if end - start >= 0.05:
                            annotation[Segment(start, end)] = "speech"
        except:
            continue  # якщо щось пішло не так — пропускаємо сегмент

    return annotation  # повертаємо розмічені сегменти (ВИПРАВЛЕНО ВІДСТУП)


# ПОШУК ФАЙЛІВ
def find_all_pairs(base_path):
    pairs = []  # список пар

    # цикл по всіх діалогах
    for dlg_num in [1, 2, 3, 4]:
        dlg = f"DLG0{dlg_num}"

        # цикл по мікрофонах
        for mic in [1, 2, 3]:
            mic_name = f"MIC{mic}"

            # цикл по дублях
            for take in [1, 2]:
                take_name = f"TAKE{take}"
                take_str = f"take{take}"

                # формування базового імені файлу
                base_name = f"Ts_Vasyl_{dlg}_{mic_name}_{take_name}"

                # шлях до папки з аудіо
                audio_dir = base_path / dlg / "audio" / mic_name

                # якщо папки немає — пропускаємо
                if not audio_dir.exists():
                    continue

                audio_path = None

                # шукаємо аудіофайл (
                for ext in ['.wav', '.WAV']:
                    candidate = audio_dir / f"{base_name}{ext}"
                    if candidate.exists():
                        audio_path = candidate
                        break

                # якщо аудіо не знайдено — пропускаємо
                if not audio_path:
                    continue

                # шукаємо TextGrid
                sync_dir = audio_dir / "sync"
                textgrid_path = None

                # спочатку перевіряємо папку sync
                if sync_dir.exists():
                    candidate = sync_dir / f"{base_name}_synced.TextGrid"
                    if candidate.exists():
                        textgrid_path = candidate

                if not textgrid_path:
                    for variant in [f"{base_name}_synced.TextGrid", f"{base_name}.TextGrid"]:
                        candidate = audio_dir / variant
                        if candidate.exists():
                            textgrid_path = candidate
                            break

                # якщо є і аудіо, і TextGrid — додаємо в список
                if audio_path and textgrid_path:
                    pairs.append({
                        'dialog': dlg,
                        'mic': mic,
                        'take': take,
                        'take_str': take_str,
                        'audio_path': audio_path,
                        'textgrid_path': textgrid_path,
                    })

    return pairs


# ОСНОВНА ПРОГРАМА
def main():
    # базова папка з даними
    BASE_PATH = Path("/Users/macbook/Documents/практика")
    # папки для результатів
    OUTPUT_DIR = BASE_PATH / "vad_results_librosa_enhanced"
    SEGMENTS_DIR = OUTPUT_DIR / "segments_reports"
    VAD_OUTPUT_DIR = OUTPUT_DIR / "vad_output_files"
    collar = 0.25  # допустиме відхилення для DER

    # створення папок
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SEGMENTS_DIR.mkdir(parents=True, exist_ok=True)
    VAD_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # пошук файлів
    pairs = find_all_pairs(BASE_PATH)

    if not pairs:
        print("Не знайдено жодної пари!")
        return

    print(f" Знайдено {len(pairs)} пар")
    print(" Обробка з використанням librosa для шумозаглушення...")

    pairs.sort(key=lambda x: (x['dialog'], x['mic'], x['take']))
    all_results = []

    # обробка кожної пари
    for idx, pair in enumerate(pairs):
        dialog = pair['dialog']
        mic = pair['mic']
        take_str = pair['take_str']
        audio_path = pair['audio_path']
        textgrid_path = pair['textgrid_path']

        # читаємо аудіо
        audio, sr = sf.read(audio_path)

        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)

        if sr != 16000:
            from scipy import signal
            num_samples = int(len(audio) * 16000 / sr)
            audio = signal.resample(audio, num_samples)
            sr = 16000

        # парсимо еталон
        ref = parse_reference_textgrid(textgrid_path)

        if len(ref) == 0:
            continue

        # обчислюємо загальну тривалість мовлення
        total_duration = 0
        for segment, _ in ref.itertracks():
            total_duration += segment.end - segment.start

        #  TEN_VAD
        ten_vad = TEN_VAD(use_librosa_enhancement=True)

        scores_ten, labels_ten = ten_vad.process_audio(audio)
        segments_ten = ten_vad.get_segments(labels_ten, scores_ten, len(audio) / sr)

        # збереження сегментів
        ten_segments_file = SEGMENTS_DIR / f"{dialog}_MIC{mic}_{take_str}_TEN_VAD_segments.txt"
        save_segments_to_txt(segments_ten, "Система 1 (TEN_VAD) - з librosa", ten_segments_file)

        # збереження frame-level результатів
        ten_vad_output_file = VAD_OUTPUT_DIR / f"{dialog}_MIC{mic}_{take_str}_TEN_VAD_vad_output.txt"
        save_vad_output_to_txt(scores_ten, labels_ten, "TEN_VAD", ten_vad_output_file)

        # формуємо гіпотезу для DER
        hyp_ten = Annotation()
        for seg in segments_ten:
            hyp_ten[Segment(seg['start'], seg['end'])] = "speech"

        # обчислюємо DER, MISS, FA
        der_ten, miss_ten, fa_ten = calculate_der_components(ref, hyp_ten, collar, total_duration)

        #  WebRTC_VAD
        webrtc_vad = WebRTC_VAD(use_librosa_enhancement=True)

        scores_webrtc, labels_webrtc = webrtc_vad.process_audio(audio)
        segments_webrtc = webrtc_vad.get_segments(labels_webrtc, scores_webrtc, len(audio) / sr)

        webrtc_segments_file = SEGMENTS_DIR / f"{dialog}_MIC{mic}_{take_str}_WebRTC_VAD_segments.txt"
        save_segments_to_txt(segments_webrtc, "Система 2 (WebRTC_VAD) - з librosa", webrtc_segments_file)

        webrtc_vad_output_file = VAD_OUTPUT_DIR / f"{dialog}_MIC{mic}_{take_str}_WebRTC_VAD_vad_output.txt"
        save_vad_output_to_txt(scores_webrtc, labels_webrtc, "WebRTC_VAD", webrtc_vad_output_file)

        hyp_webrtc = Annotation()
        for seg in segments_webrtc:
            hyp_webrtc[Segment(seg['start'], seg['end'])] = "speech"

        der_webrtc, miss_webrtc, fa_webrtc = calculate_der_components(ref, hyp_webrtc, collar, total_duration)

        # вивід у консоль
        print(f"\n{dialog} | MIC{mic} | {take_str}")
        print(
            f"  TEN_VAD:     DER={der_ten:.1f}%, MISS={miss_ten:.1f}%, FA={fa_ten:.1f}%, сегментів={len(segments_ten)}")
        print(
            f"  WebRTC_VAD:  DER={der_webrtc:.1f}%, MISS={miss_webrtc:.1f}%, FA={fa_webrtc:.1f}%, сегментів={len(segments_webrtc)}")

        # збереження результатів
        all_results.append({
            'dialog': dialog,
            'mic': mic,
            'take': take_str,
            'vad_name': 'TEN_VAD',
            'der_percent': round(der_ten, 1),
            'miss_percent': round(miss_ten, 1),
            'fa_percent': round(fa_ten, 1),
            'num_segments': len(segments_ten)
        })

        all_results.append({
            'dialog': dialog,
            'mic': mic,
            'take': take_str,
            'vad_name': 'WebRTC_VAD',
            'der_percent': round(der_webrtc, 1),
            'miss_percent': round(miss_webrtc, 1),
            'fa_percent': round(fa_webrtc, 1),
            'num_segments': len(segments_webrtc)
        })

    if all_results:
        summary_file = OUTPUT_DIR / 'summary_report.txt'
        save_summary_table(all_results, summary_file)

        import pandas as pd
        df = pd.DataFrame(all_results)
        df.to_csv(OUTPUT_DIR / 'vad_comparison_results.csv', index=False, encoding='utf-8')

        print(f"\n ОБРОБКУ ЗАВЕРШЕНО")
        print(f" Результати збережено в: {OUTPUT_DIR}")
    else:
        print(" Немає результатів для збереження!")


# запуск програми
if __name__ == "__main__":
    main()