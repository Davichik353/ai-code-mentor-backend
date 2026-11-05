"""Curated bilingual exercises. Answers/hints are only exposed by gated routes."""

def text(ru, uz):
    return {"ru": ru, "uz": uz}


def exercise(key, language, title, prompt, starter, tests, hints, solution, change):
    return dict(id=key, language=language, title=title, prompt=prompt, starter_code=starter,
                tests=tests, hints=hints, solution=solution,
                defense_questions=[text("Объясните ход решения и выбор операций.", "Yechim bosqichlari va amallar tanlovini tushuntiring."),
                                   text("Какой граничный случай вы проверили и почему?", "Qaysi chegaraviy holatni tekshirdingiz va nima uchun?")],
                change=change)

SUM_HINTS = [text("Сколько значений вы получаете из ввода?", "Kiritishda nechta qiymat olasiz?"),
             text("Ввод сначала является строкой. Какие типы нужны для сложения?", "Kiritilgan qiymat avval matn bo‘ladi. Qo‘shish uchun qanday tur kerak?"),
             text("Преобразуйте оба значения в числа и проверьте результат на отрицательных числах.", "Ikkala qiymatni songa aylantiring va manfiy sonlar bilan tekshiring.")]
MAX_HINTS = [text("Может ли максимальное число быть отрицательным?", "Eng katta son manfiy bo‘lishi mumkinmi?"),
             text("Не начинайте с нуля: это даст ошибку на полностью отрицательном наборе.", "Noldan boshlamang: barcha sonlar manfiy bo‘lsa, xato chiqadi."),
             text("Начните с первого числа и сравните с остальными либо используйте max.", "Birinchi sondan boshlang va qolganlari bilan solishtiring yoki max dan foydalaning.")]
VOWEL_HINTS = [text("Одинаково ли считаются заглавные и строчные буквы?", "Katta va kichik harflar bir xil sanaladimi?"),
               text("Сначала приведите строку к одному регистру; учитывайте только a, e, i, o, u.", "Avval matnni kichik harflarga o‘tkazing; faqat a, e, i, o, u ni hisoblang."),
               text("Переберите символы и увеличивайте счётчик для гласных.", "Belgilarni tekshirib, unli harf bo‘lsa, hisoblagichni oshiring.")]
TEMPLATES = {}
for lang, ext in [("Python", "py"), ("JavaScript", "js")]:
    cases = [
        ("sum", text("Сумма двух чисел", "Ikki son yig‘indisi"),
         text("Прочитайте два целых числа из двух строк. Выведите только их сумму.", "Ikki qatordan ikkita butun sonni o‘qing. Faqat ularning yig‘indisini chiqaring."),
         "a = input()\nb = input()\n# TODO\n" if ext == "py" else "const a = prompt();\nconst b = prompt();\n// TODO\n",
         [{"stdin": "2\n3", "expected_stdout": "5"}, {"stdin": "-4\n-6", "expected_stdout": "-10"}, {"stdin": "0\n7", "expected_stdout": "7"}],
         SUM_HINTS, "a = int(input())\nb = int(input())\nprint(a + b)" if ext == "py" else "const a = Number(prompt());\nconst b = Number(prompt());\nconsole.log(a + b);",
         text("Измените программу: прочитайте третье число и выведите сумму трёх чисел. Объясните изменение.", "Dasturni o‘zgartiring: uchinchi sonni o‘qib, uchta son yig‘indisini chiqaring. O‘zgarishni tushuntiring.")),
        ("maximum", text("Максимум, включая отрицательные числа", "Manfiy sonlar orasida ham eng kattasi"),
         text("В одной строке дан непустой список целых чисел через пробел. Выведите наибольшее число.", "Bir qatorda bo‘sh joy bilan ajratilgan butun sonlar berilgan. Eng katta sonni chiqaring."),
         "numbers = input().split()\n# TODO\n" if ext == "py" else "const numbers = prompt().split(' ');\n// TODO\n",
         [{"stdin": "3 8 2", "expected_stdout": "8"}, {"stdin": "-9 -2 -7", "expected_stdout": "-2"}, {"stdin": "4", "expected_stdout": "4"}],
         MAX_HINTS, "numbers = list(map(int, input().split()))\nprint(max(numbers))" if ext == "py" else "const numbers = prompt().split(/\\s+/).map(Number);\nconsole.log(Math.max(...numbers));",
         text("Выведите теперь минимальное число вместо максимального. Объясните, что изменили.", "Endi eng katta son o‘rniga eng kichik sonni chiqaring. O‘zgarishni tushuntiring.")),
        ("vowels", text("Счётчик гласных", "Unli harflar hisoblagichi"),
         text("Прочитайте строку. Выведите количество латинских гласных a, e, i, o, u без учёта регистра. Остальные символы игнорируйте.", "Matnni o‘qing. Katta-kichik harf farqisiz a, e, i, o, u unlilari sonini chiqaring. Qolgan belgilarni hisoblamang."),
         "text = input()\n# TODO\n" if ext == "py" else "const text = prompt();\n// TODO\n",
         [{"stdin": "Hello", "expected_stdout": "2"}, {"stdin": "AEIOU", "expected_stdout": "5"}, {"stdin": "rhythm 123", "expected_stdout": "0"}],
         VOWEL_HINTS, "text = input().lower()\nprint(sum(1 for ch in text if ch in 'aeiou'))" if ext == "py" else "const text = prompt().toLowerCase();\nconsole.log([...text].filter(ch => 'aeiou'.includes(ch)).length);",
         text("Дополнительно выведите число цифр в строке. Объясните, как отличаете цифры от букв.", "Matndagi raqamlar sonini ham chiqaring. Raqamlarni harflardan qanday ajratganingizni tushuntiring.")),
    ]
    for key, title, prompt, starter, tests, hints, solution, change in cases:
        item = exercise(f"{key}-{ext}", lang, title, prompt, starter, tests, hints, solution, change)
        TEMPLATES[item["id"]] = item

GLOSSARY = [
    {"term": "variable", **text("Переменная хранит значение: например, возраст или имя.", "O‘zgaruvchi qiymatni saqlaydi: masalan, yosh yoki ism.")},
    {"term": "loop", **text("Цикл повторяет действие для нескольких значений или пока верно условие.", "Sikl amalni bir necha qiymat uchun yoki shart bajarilguncha takrorlaydi.")},
    {"term": "edge case", **text("Граничный случай — необычный ввод: ноль, отрицательные числа, один элемент.", "Chegaraviy holat — nol, manfiy son yoki bitta element kabi maxsus kiritish.")},
    {"term": "test", **text("Тест сравнивает результат программы с ожидаемым результатом для заданного ввода.", "Test ma’lum kiritish uchun dastur natijasini kutilgan natija bilan solishtiradi.")},
    {"term": "type", **text("Тип определяет, является значение числом, строкой или другим объектом.", "Tur qiymatning son, matn yoki boshqa obyekt ekanini belgilaydi.")},
]
