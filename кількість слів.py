from pathlib import Path
import re

# базовий шлях
base_path = Path(".")

# Список діалогів, які обробляються
dialogues = ['DLG01', 'DLG02', 'DLG03', 'DLG04']
# Загальні лічильники для обох мовців 
total_A = 0
total_B = 0

# функція для очищення тексту
def clean_text(text):
    # прибираємо [перекривання] та інші ремарки
    text = re.sub(r"\[.*?\]", "", text)
    return text

# проходимо по всіх діалогах
for dlg in dialogues:
    scripts_path = base_path / dlg / "scripts"
    if not scripts_path.exists():
        print(f"{dlg}: папка scripts не знайдена")
        continue
    print(f"\n{dlg}:")

    dlg_A = 0
    dlg_B = 0

    # перебираємо всі txt файли
    for file in scripts_path.glob("*"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            file_A = 0
            file_B = 0

            # аналізуємо кожен рядок
            for line in lines:
                line = line.strip()

                # репліки A
                if line.startswith("А:"):
                    text = line[2:].strip()
                    text = clean_text(text)

                    words = text.split()
                    file_A += len(words)

                # репліки Б
                elif line.startswith("Б:"):
                    text = line[2:].strip()
                    text = clean_text(text)

                    words = text.split()
                    file_B += len(words)

            print(f"  {file.name}: A={file_A}, Б={file_B}")

            dlg_A += file_A
            dlg_B += file_B

        except Exception as e:
            print(f"  {file.name}: ERROR ({e})")

    total_A += dlg_A
    total_B += dlg_B

# загальний результат
print("\nЗАГАЛОМ:")
print(f"A: {total_A} слів")
print(f"Б: {total_B} слів")
