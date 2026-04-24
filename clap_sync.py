import textgrid
from pathlib import Path

# Шлях до всіх діалогів
base_path = Path(".")

# Список діалогів та takes, які потрібно обробити
dialogues = ['DLG01', 'DLG02', 'DLG03', 'DLG04']
takes = ['TAKE1', 'TAKE2']

# Лічильники для статистики
processed_count = 0  # кількість успішно оброблених take
error_count = 0      # кількість take з помилками
skipped_count = 0    # кількість пропущених take

# Функція для створення синхронізованого файлу
def create_synced_file(mic3_tg, target_tg, offset, output_path):
    try:
        # Обчислюємо нові часові межі на основі зсунутих даних з MIC3
        new_min_time = mic3_tg.minTime + offset
        if new_min_time < 0:
            new_min_time = 0

        # Знаходимо максимальний час серед зсунутих інтервалів MIC3
        max_time_from_mic3 = mic3_tg.maxTime + offset

        # Використовуємо максимальний час з target_tg (оригінальний MIC1/MIC2)
        new_max_time = max(max_time_from_mic3, target_tg.maxTime)

        # Створюємо новий TextGrid
        new_tg = textgrid.TextGrid(minTime=new_min_time, maxTime=new_max_time)

        # Копіюємо перші 4 рівні з MIC3 зі зсувом
        for i in range(min(4, len(mic3_tg.tiers))):
            source_tier = mic3_tg.tiers[i]

            # Створюємо новий tier
            new_tier = textgrid.IntervalTier(
                name=source_tier.name,
                minTime=new_min_time,
                maxTime=new_max_time
            )

            # Додаємо всі інтервали зі зсувом
            for interval in source_tier:
                if interval.mark and interval.mark.strip():
                    new_min = interval.minTime + offset
                    new_max = interval.maxTime + offset

                    # Додаємо інтервал тільки якщо він в межах нового TextGrid
                    if new_max > new_min and new_min >= new_min_time:
                        new_tier.add(new_min, new_max, interval.mark)

            new_tg.tiers.append(new_tier)

        # Додаємо 5-й рівень clap-sync з target_tg
        if len(target_tg.tiers) > 4:
            clap_source = target_tg.tiers[4]

            # Створюємо tier для clap-sync
            clap_tier = textgrid.IntervalTier(
                name="clap-sync",
                minTime=clap_source.minTime,
                maxTime=clap_source.maxTime
            )

            # Копіюємо всі інтервали з оригінального clap-sync
            for interval in clap_source:
                if interval.mark and interval.mark.strip():
                    clap_tier.add(interval.minTime, interval.maxTime, interval.mark)

            new_tg.tiers.append(clap_tier)
        else:
            # Якщо немає 5-го рівня, створюємо порожній
            clap_tier = textgrid.IntervalTier(
                name="clap-sync",
                minTime=0,
                maxTime=0
            )
            new_tg.tiers.append(clap_tier)

        # Записуємо файл
        new_tg.write(str(output_path))
        return True

    except Exception as e:
        print(f"    Error: {e}")
        import traceback
        traceback.print_exc()
        return False


# Основний цикл
for dlg in dialogues:
    print(f"\n{dlg}:")

    for take in takes:
        # Шляхи до папок
        mic1_path = base_path / dlg / 'audio' / 'MIC1'
        mic2_path = base_path / dlg / 'audio' / 'MIC2'
        mic3_path = base_path / dlg / 'audio' / 'MIC3'

        # Перевірка наявності папок
        if not mic3_path.exists() or not mic1_path.exists() or not mic2_path.exists():
            print(f"  {take}: Missing folder")
            skipped_count += 1
            continue

        # Шляхи до файлів
        mic3_file = mic3_path / f"Ts_Vasyl_{dlg}_MIC3_{take}.TextGrid"
        mic1_file = mic1_path / f"Ts_Vasyl_{dlg}_MIC1_{take}.TextGrid"
        mic2_file = mic2_path / f"Ts_Vasyl_{dlg}_MIC2_{take}.TextGrid"

        # Перевірка існування файлів
        if not all(f.exists() for f in [mic3_file, mic1_file, mic2_file]):
            print(f"  {take}: Missing file")
            skipped_count += 1
            continue

        try:
            print(f"  {take}:")

            # Зчитування файлів
            tg3 = textgrid.TextGrid.fromFile(str(mic3_file))
            tg1 = textgrid.TextGrid.fromFile(str(mic1_file))
            tg2 = textgrid.TextGrid.fromFile(str(mic2_file))


            # Функція для пошуку clap
            def find_clap(tg):
                if len(tg.tiers) <= 4:
                    return None
                tier = tg.tiers[4]
                for interval in tier:
                    if interval.mark and interval.mark.strip().lower() == 'clap':
                        return interval.minTime
                return None

            # Знаходимо час clap
            t3 = find_clap(tg3)
            t1 = find_clap(tg1)
            t2 = find_clap(tg2)

            if None in [t3, t1, t2]:
                missing = []
                if t3 is None: missing.append("MIC3")
                if t1 is None: missing.append("MIC1")
                if t2 is None: missing.append("MIC2")
                print(f"  Clap missing in: {', '.join(missing)}")
                error_count += 1
                continue

            # Обчислюємо зсуви для MIC1 і MIC2 відносно MIC3
            offset1 = t1 - t3
            offset2 = t2 - t3

            print(f"  Clap times: MIC3={t3:.3f}s, MIC1={t1:.3f}s, MIC2={t2:.3f}s")
            print(f"  Offsets: MIC1={offset1:+.3f}s, MIC2={offset2:+.3f}s")

            # Формуємо назви вихідних файлів
            out1 = mic1_path / mic1_file.name.replace('.TextGrid', '_synced.TextGrid')
            out2 = mic2_path / mic2_file.name.replace('.TextGrid', '_synced.TextGrid')

            # Створюємо синхронізовані файли
            success1 = create_synced_file(tg3, tg1, offset1, out1)
            success2 = create_synced_file(tg3, tg2, offset2, out2)

            if success1 and success2:
                print(f"  Saved: {out1.name}")
                print(f"  Saved: {out2.name}")
                processed_count += 1
            else:
                print(f"  Error creating synced files")
                error_count += 1

        except Exception as e:
            print(f"  Error: {e}")
            import traceback

            traceback.print_exc()
            error_count += 1

# Підсумкова статистика
print(f"\nSUMMARY")
print(f"Successfully processed: {processed_count} take(s)")
print(f"Errors: {error_count}")
print(f"Skipped: {skipped_count}")
print("Done!")
