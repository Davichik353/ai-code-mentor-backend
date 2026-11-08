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

# A helper keeps metadata consistent across the catalog without changing legacy IDs.
CATEGORIES = [
    {"id": "basics", "title": text("Ввод и вычисления", "Kiritish va hisoblash")},
    {"id": "conditions", "title": text("Условия", "Shartlar")},
    {"id": "loops", "title": text("Циклы", "Sikllar")},
    {"id": "strings", "title": text("Строки", "Matnlar")},
    {"id": "lists", "title": text("Списки", "Ro‘yxatlar")},
    {"id": "logic", "title": text("Логика", "Mantiq")},
]
DIFFICULTIES = [
    {"id": "beginner", "title": text("Новичок", "Boshlang‘ich")},
    {"id": "intermediate", "title": text("Продолжающий", "O‘rta daraja")},
]
_CATEGORY_TITLES = {item['id']: item['title'] for item in CATEGORIES}
_DIFFICULTY_TITLES = {item['id']: item['title'] for item in DIFFICULTIES}


def _metadata(item, category, difficulty):
    item.update(category=category, category_title=_CATEGORY_TITLES[category],
                difficulty=difficulty, difficulty_title=_DIFFICULTY_TITLES[difficulty])
    return item


for _item in TEMPLATES.values():
    _topic = _item['id'].rsplit('-', 1)[0]
    _metadata(_item, {'sum': 'basics', 'maximum': 'lists', 'vowels': 'strings'}[_topic], 'beginner')


def _tests(*pairs):
    return [{'stdin': stdin, 'expected_stdout': expected} for stdin, expected in pairs]


def _hints(first_ru, first_uz, second_ru, second_uz, third_ru, third_uz):
    return [text(first_ru, first_uz), text(second_ru, second_uz), text(third_ru, third_uz)]


# Original exercises on standard introductory topics. Source-topic notes are in EXERCISE_SOURCES.md.
_NEW_TOPICS = [
    dict(key='perimeter', category='basics', difficulty='beginner',
         title=text('Длина рамки', 'Ramka uzunligi'),
         prompt=text('Для прямоугольной рамки даны длина и ширина — два целых числа от 1 до 100000, каждое в своей строке. Выведите общую длину четырёх сторон.',
                     'To‘g‘ri to‘rtburchak ramkaning uzunligi va eni berilgan: 1 dan 100000 gacha ikkita butun son, har biri alohida qatorda. To‘rt tomonning umumiy uzunligini chiqaring.'),
         py_starter='length = int(input())\nwidth = int(input())\n# TODO\n',
         js_starter='const length = Number(prompt());\nconst width = Number(prompt());\n// TODO\n',
         tests=_tests(('7\n3', '20'), ('1\n1', '4'), ('100000\n2', '200004')),
         hints=_hints('Сколько сторон каждой длины есть у рамки?', 'Ramkada har bir uzunlikdagi nechta tomon bor?',
                      'Сложите длину и ширину. Эту пару нужно учесть дважды.', 'Uzunlik va enni qo‘shing. Bu juftlik ikki marta hisoblanadi.',
                      'Периметр равен 2 × (длина + ширина). Выведите одно число.', 'Perimetr 2 × (uzunlik + en) ga teng. Bitta son chiqaring.'),
         py='length = int(input())\nwidth = int(input())\nprint(2 * (length + width))',
         js='const length = Number(prompt());\nconst width = Number(prompt());\nconsole.log(2 * (length + width));',
         change=text('Теперь выведите площадь этого прямоугольника. Объясните, почему формула другая.',
                     'Endi shu to‘g‘ri to‘rtburchakning yuzini chiqaring. Formula nega boshqacha ekanini tushuntiring.')),
    dict(key='minutes', category='basics', difficulty='beginner',
         title=text('Часы и оставшиеся минуты', 'Soat va qolgan daqiqalar'),
         prompt=text('Дано целое количество минут от 0 до 100000. Выведите количество полных часов и оставшиеся минуты в одной строке через пробел. Часы не ограничивайте сутками.',
                     '0 dan 100000 gacha butun daqiqalar soni berilgan. To‘liq soatlar va qolgan daqiqalarni bir qatorda bo‘sh joy bilan chiqaring. Soatlarni bir sutka bilan cheklamang.'),
         py_starter='minutes = int(input())\n# TODO\n', js_starter='const minutes = Number(prompt());\n// TODO\n',
         tests=_tests(('125', '2 5'), ('0', '0 0'), ('60', '1 0'), ('1501', '25 1')),
         hints=_hints('Сколько минут содержит один полный час?', 'Bir to‘liq soatda nechta daqiqa bor?',
                      'Полные часы даёт целая часть деления на 60.', 'To‘liq soatlarni 60 ga bo‘lishning butun qismi beradi.',
                      'Найдите частное и остаток от деления на 60.', '60 ga bo‘lgandagi butun qism va qoldiqni toping.'),
         py='minutes = int(input())\nprint(minutes // 60, minutes % 60)',
         js='const minutes = Number(prompt());\nconsole.log(Math.floor(minutes / 60), minutes % 60);',
         change=text('Прочитайте количество секунд и выведите минуты и оставшиеся секунды. Объясните сходство решения.',
                     'Soniyalar sonini o‘qing va daqiqalar hamda qolgan soniyalarni chiqaring. Yechimdagi o‘xshashlikni tushuntiring.')),
    dict(key='parity', category='conditions', difficulty='beginner',
         title=text('Чётное или нечётное', 'Juft yoki toq'),
         prompt=text('Прочитайте целое число от −1000000 до 1000000. Выведите EVEN, если оно чётное, иначе ODD. Ноль считается чётным.',
                     '−1000000 dan 1000000 gacha butun sonni o‘qing. Juft bo‘lsa EVEN, aks holda ODD chiqaring. Nol juft son hisoblanadi.'),
         py_starter='number = int(input())\n# TODO\n', js_starter='const number = Number(prompt());\n// TODO\n',
         tests=_tests(('8', 'EVEN'), ('-3', 'ODD'), ('0', 'EVEN'), ('-12', 'EVEN')),
         hints=_hints('Как проверить делимость числа на 2?', 'Sonning 2 ga bo‘linishini qanday tekshirish mumkin?',
                      'У чётного числа остаток от деления на 2 равен нулю.', 'Juft sonni 2 ga bo‘lgandagi qoldiq nolga teng.',
                      'Сравните number % 2 с нулём и выберите нужное слово.', 'number % 2 ni nol bilan solishtiring va kerakli so‘zni tanlang.'),
         py='number = int(input())\nprint("EVEN" if number % 2 == 0 else "ODD")',
         js='const number = Number(prompt());\nconsole.log(number % 2 === 0 ? "EVEN" : "ODD");',
         change=text('Проверьте вместо чётности делимость на 3 и выводите YES или NO. Объясните изменение условия.',
                     'Juftlik o‘rniga 3 ga bo‘linishni tekshiring va YES yoki NO chiqaring. Shartdagi o‘zgarishni tushuntiring.')),
    dict(key='sign', category='conditions', difficulty='beginner',
         title=text('Три случая для числа', 'Sonning uch holati'),
         prompt=text('Прочитайте целое число от −1000000 до 1000000. Для отрицательного выведите NEGATIVE, для нуля ZERO, для положительного POSITIVE.',
                     '−1000000 dan 1000000 gacha butun sonni o‘qing. Manfiy bo‘lsa NEGATIVE, nol bo‘lsa ZERO, musbat bo‘lsa POSITIVE chiqaring.'),
         py_starter='number = int(input())\n# TODO\n', js_starter='const number = Number(prompt());\n// TODO\n',
         tests=_tests(('-7', 'NEGATIVE'), ('0', 'ZERO'), ('11', 'POSITIVE')),
         hints=_hints('Нужны два или три разных ответа?', 'Ikki yoki uch xil javob kerakmi?',
                      'Ноль выделите в самостоятельную ветку условия.', 'Nol uchun alohida shart tarmog‘ini ajrating.',
                      'Сначала проверьте число < 0, затем число == 0, иначе оно положительное.', 'Avval son < 0, keyin son == 0 shartini tekshiring; aks holda u musbat.'),
         py='number = int(input())\nif number < 0:\n    print("NEGATIVE")\nelif number == 0:\n    print("ZERO")\nelse:\n    print("POSITIVE")',
         js='const number = Number(prompt());\nif (number < 0) console.log("NEGATIVE");\nelse if (number === 0) console.log("ZERO");\nelse console.log("POSITIVE");',
         change=text('Дополнительно выведите абсолютную величину числа во второй строке. Объясните случай отрицательного ввода.',
                     'Ikkinchi qatorda sonning modulini ham chiqaring. Manfiy son kiritilgan holatni tushuntiring.')),
    dict(key='leap-year', category='conditions', difficulty='intermediate',
         title=text('День для високосного года', 'Kabisa yilidagi kun'),
         prompt=text('Дан год от 1600 до 9999. По григорианскому правилу год високосный, если делится на 400 либо делится на 4, но не на 100. Выведите YES или NO.',
                     '1600 dan 9999 gacha yil berilgan. Grigoriy qoidasiga ko‘ra, 400 ga bo‘linadigan yoki 4 ga bo‘linib 100 ga bo‘linmaydigan yil kabisa yilidir. YES yoki NO chiqaring.'),
         py_starter='year = int(input())\n# TODO\n', js_starter='const year = Number(prompt());\n// TODO\n',
         tests=_tests(('2024', 'YES'), ('1900', 'NO'), ('2000', 'YES'), ('2023', 'NO')),
         hints=_hints('Все ли годы, кратные 4, подходят?', '4 ga karrali barcha yillar mos keladimi?',
                      'Столетия проверяются отдельно: 1900 и 2000 дают разные ответы.', 'Asr yillari alohida tekshiriladi: 1900 va 2000 turli javob beradi.',
                      'Соедините условие делимости на 400 с парой: делится на 4 и не делится на 100.', '400 ga bo‘linish shartini 4 ga bo‘linish va 100 ga bo‘linmaslik juftligi bilan birlashtiring.'),
         py='year = int(input())\nprint("YES" if year % 400 == 0 or (year % 4 == 0 and year % 100 != 0) else "NO")',
         js='const year = Number(prompt());\nconsole.log(year % 400 === 0 || (year % 4 === 0 && year % 100 !== 0) ? "YES" : "NO");',
         change=text('Выведите число дней в феврале этого года: 28 или 29. Объясните повторное использование условия.',
                     'Shu yil fevral oyidagi kunlar sonini chiqaring: 28 yoki 29. Shartdan qayta foydalanishni tushuntiring.')),
    dict(key='sum-range', category='loops', difficulty='beginner',
         title=text('Сумма от одного до n', 'Birdan n gacha yig‘indi'),
         prompt=text('Дано целое n от 0 до 10000. Выведите сумму всех целых чисел от 1 до n включительно. При n = 0 сумма равна нулю. Попробуйте решить с циклом.',
                     '0 dan 10000 gacha butun n berilgan. 1 dan n gacha barcha butun sonlar yig‘indisini chiqaring. n = 0 bo‘lsa, yig‘indi nol. Sikl bilan yechishga urinib ko‘ring.'),
         py_starter='n = int(input())\ntotal = 0\n# TODO\n', js_starter='const n = Number(prompt());\nlet total = 0;\n// TODO\n',
         tests=_tests(('5', '15'), ('0', '0'), ('1', '1'), ('100', '5050')),
         hints=_hints('Какое начальное значение должно быть у суммы?', 'Yig‘indining boshlang‘ich qiymati qanday bo‘lishi kerak?',
                      'Добавляйте к сумме каждое число от 1 до n. Не потеряйте последнее число.', 'Yig‘indiga 1 dan n gacha har bir sonni qo‘shing. Oxirgi sonni unutmay qo‘shing.',
                      'Начните с total = 0 и используйте включительную верхнюю границу n.', 'total = 0 dan boshlang va n ni ham qamrab oladigan yuqori chegaradan foydalaning.'),
         py='n = int(input())\ntotal = 0\nfor value in range(1, n + 1):\n    total += value\nprint(total)',
         js='const n = Number(prompt());\nlet total = 0;\nfor (let value = 1; value <= n; value++) total += value;\nconsole.log(total);',
         change=text('Суммируйте только чётные числа от 1 до n. Объясните, как изменили цикл или условие.',
                     '1 dan n gacha faqat juft sonlarni yig‘ing. Sikl yoki shartni qanday o‘zgartirganingizni tushuntiring.')),
    dict(key='factorial', category='loops', difficulty='beginner',
         title=text('Произведение первых чисел', 'Dastlabki sonlar ko‘paytmasi'),
         prompt=text('Прочитайте n от 0 до 12. Выведите произведение чисел от 1 до n. Для n = 0 результат по определению равен 1. Используйте цикл.',
                     '0 dan 12 gacha n ni o‘qing. 1 dan n gacha sonlar ko‘paytmasini chiqaring. n = 0 uchun natija ta’rif bo‘yicha 1. Sikldan foydalaning.'),
         py_starter='n = int(input())\nproduct = 1\n# TODO\n', js_starter='const n = Number(prompt());\nlet product = 1;\n// TODO\n',
         tests=_tests(('5', '120'), ('0', '1'), ('1', '1'), ('12', '479001600')),
         hints=_hints('Почему произведение нельзя начинать с нуля?', 'Nega ko‘paytmani noldan boshlash mumkin emas?',
                      'Единица не меняет результат умножения и подходит для пустого набора.', 'Birga ko‘paytirish natijani o‘zgartirmaydi va bo‘sh to‘plam uchun mos keladi.',
                      'Последовательно умножайте product на числа от 1 до n.', 'product ni ketma-ket 1 dan n gacha sonlarga ko‘paytiring.'),
         py='n = int(input())\nproduct = 1\nfor value in range(1, n + 1):\n    product *= value\nprint(product)',
         js='const n = Number(prompt());\nlet product = 1;\nfor (let value = 1; value <= n; value++) product *= value;\nconsole.log(product);',
         change=text('Вычислите произведение только нечётных чисел от 1 до n. Проверьте n = 0 и n = 4.',
                     '1 dan n gacha faqat toq sonlar ko‘paytmasini hisoblang. n = 0 va n = 4 ni tekshiring.')),
    dict(key='digit-sum', category='loops', difficulty='intermediate',
         title=text('Сумма десятичных цифр', 'O‘nlik raqamlar yig‘indisi'),
         prompt=text('Дано неотрицательное целое число не больше 1000000000. Выведите сумму его десятичных цифр. Решите задачу с помощью остатка и целочисленного деления.',
                     '1000000000 dan katta bo‘lmagan manfiy bo‘lmagan butun son berilgan. Uning o‘nlik raqamlari yig‘indisini chiqaring. Qoldiq va butun bo‘lish yordamida yeching.'),
         py_starter='number = int(input())\ntotal = 0\n# TODO\n', js_starter='let number = Number(prompt());\nlet total = 0;\n// TODO\n',
         tests=_tests(('5072', '14'), ('0', '0'), ('1000000000', '1'), ('999', '27')),
         hints=_hints('Какая операция даёт последнюю цифру числа?', 'Qaysi amal sonning oxirgi raqamini beradi?',
                      'Остаток при делении на 10 — последняя цифра; целое деление на 10 удаляет её.', '10 ga bo‘lgandagi qoldiq oxirgi raqamdir; butun bo‘lish esa uni olib tashlaydi.',
                      'Пока число больше нуля, прибавляйте остаток от деления на 10 и уменьшайте число целым делением.', 'Son noldan katta ekan, 10 ga bo‘lish qoldig‘ini qo‘shing va sonni butun bo‘lish bilan kamaytiring.'),
         py='number = int(input())\ntotal = 0\nwhile number > 0:\n    total += number % 10\n    number //= 10\nprint(total)',
         js='let number = Number(prompt());\nlet total = 0;\nwhile (number > 0) {\n  total += number % 10;\n  number = Math.floor(number / 10);\n}\nconsole.log(total);',
         change=text('Найдите наибольшую цифру вместо суммы. Объясните начальное значение и случай нуля.',
                     'Yig‘indi o‘rniga eng katta raqamni toping. Boshlang‘ich qiymat va nol holatini tushuntiring.')),
    dict(key='word-count', category='strings', difficulty='beginner',
         title=text('Сколько слов в строке', 'Qatordagi so‘zlar soni'),
         prompt=text('Прочитайте одну строку длиной от 1 до 200 символов. Слова разделены одним или несколькими пробелами; пробелы могут стоять по краям. Выведите число слов. Строка из одних пробелов содержит ноль слов.',
                     '1 dan 200 tagacha belgidan iborat bitta qatorni o‘qing. So‘zlar bir yoki bir nechta bo‘sh joy bilan ajratilgan; chetlarda ham bo‘sh joy bo‘lishi mumkin. So‘zlar sonini chiqaring. Faqat bo‘sh joylardan iborat qatorda nol so‘z bor.'),
         py_starter='line = input()\n# TODO\n', js_starter='const line = prompt();\n// TODO\n',
         tests=_tests(('one two three', '3'), ('  one   two  ', '2'), ('single', '1'), ('   ', '0')),
         hints=_hints('Число пробелов всегда равно числу слов минус один?', 'Bo‘sh joylar soni har doim so‘zlar sonidan bittaga kammi?',
                      'Соседние пробелы не должны создавать пустые слова.', 'Ketma-ket bo‘sh joylar bo‘sh so‘zlar yaratmasligi kerak.',
                      'Разбейте строку по группам пробелов. Отдельно учтите строку без слов.', 'Qatorni bo‘sh joylar guruhlari bo‘yicha ajrating. So‘zsiz qatorni alohida hisobga oling.'),
         py='line = input()\nprint(len(line.split()))',
         js='const line = prompt().trim();\nconsole.log(line === "" ? 0 : line.split(/\\s+/).length);',
         change=text('Выведите длину самого длинного слова; для строки без слов выведите 0. Объясните обработку пустого списка.',
                     'Eng uzun so‘z uzunligini chiqaring; so‘zsiz qator uchun 0 chiqaring. Bo‘sh ro‘yxat qanday qayta ishlanishini tushuntiring.')),
    dict(key='reverse-text', category='strings', difficulty='beginner',
         title=text('Строка в обратном порядке', 'Teskari tartibdagi matn'),
         prompt=text('Прочитайте строку из 1–100 латинских букв и пробелов. Выведите её символы в обратном порядке, сохранив регистр и все пробелы.',
                     '1–100 ta lotin harfi va bo‘sh joydan iborat qatorni o‘qing. Harflar registri va barcha bo‘sh joylarni saqlab, belgilarni teskari tartibda chiqaring.'),
         py_starter='line = input()\n# TODO\n', js_starter='const line = prompt();\n// TODO\n',
         tests=_tests(('stressed', 'desserts'), ('a', 'a'), ('ab cd', 'dc ba')),
         hints=_hints('Какой символ должен оказаться первым в ответе?', 'Javobda qaysi belgi birinchi bo‘lishi kerak?',
                      'Перебирайте исходные символы от последнего к первому.', 'Asl belgilarni oxirgisidan birinchisigacha ko‘rib chiqing.',
                      'Используйте обратный срез в Python либо массив символов и reverse в JavaScript.', 'Python da teskari kesim yoki JavaScript da belgilar massivi va reverse dan foydalaning.'),
         py='line = input()\nprint(line[::-1])',
         js='const line = prompt();\nconsole.log([...line].reverse().join(""));',
         change=text('Проверьте, совпадает ли строка со своей обратной записью. Выведите YES или NO; регистр и пробелы учитывайте.',
                     'Qator teskari yozuvi bilan bir xil ekanini tekshiring. YES yoki NO chiqaring; registr va bo‘sh joylarni hisobga oling.')),
    dict(key='positive-count', category='lists', difficulty='beginner',
         title=text('Сколько положительных значений', 'Musbat qiymatlar soni'),
         prompt=text('В одной строке дан непустой список целых чисел через пробел. Выведите количество чисел, строго больших нуля. Ноль не считайте положительным.',
                     'Bir qatorda bo‘sh joy bilan ajratilgan bo‘sh bo‘lmagan butun sonlar ro‘yxati berilgan. Noldan qat’iy katta sonlar sonini chiqaring. Nolni musbat deb hisoblamang.'),
         py_starter='numbers = list(map(int, input().split()))\n# TODO\n', js_starter='const numbers = prompt().trim().split(/\\s+/).map(Number);\n// TODO\n',
         tests=_tests(('-2 0 3 5', '2'), ('-4 -1', '0'), ('0', '0'), ('1 2 3', '3')),
         hints=_hints('Нужно складывать числа или считать подходящие элементы?', 'Sonlarni qo‘shish kerakmi yoki mos elementlarni sanash kerakmi?',
                      'Для каждого элемента проверьте строгое условие > 0.', 'Har bir element uchun > 0 qat’iy shartini tekshiring.',
                      'Увеличивайте счётчик на 1 только для положительных элементов.', 'Hisoblagichni faqat musbat elementlar uchun 1 ga oshiring.'),
         py='numbers = list(map(int, input().split()))\nprint(sum(1 for number in numbers if number > 0))',
         js='const numbers = prompt().trim().split(/\\s+/).map(Number);\nconsole.log(numbers.filter(number => number > 0).length);',
         change=text('Посчитайте отрицательные значения вместо положительных. Объясните, что произойдёт с нулём.',
                     'Musbat qiymatlar o‘rniga manfiylarini sanang. Nol qanday hisoblanishini tushuntiring.')),
    dict(key='even-sum', category='lists', difficulty='beginner',
         title=text('Сумма чётных элементов', 'Juft elementlar yig‘indisi'),
         prompt=text('Прочитайте непустой список целых чисел от −10000 до 10000 в одной строке через пробел. Выведите сумму его чётных элементов. Если таких нет, выведите 0.',
                     'Bir qatorda bo‘sh joy bilan ajratilgan −10000 dan 10000 gacha butun sonlarning bo‘sh bo‘lmagan ro‘yxatini o‘qing. Juft elementlar yig‘indisini chiqaring. Bunday elementlar bo‘lmasa, 0 chiqaring.'),
         py_starter='numbers = list(map(int, input().split()))\n# TODO\n', js_starter='const numbers = prompt().trim().split(/\\s+/).map(Number);\n// TODO\n',
         tests=_tests(('1 2 3 4', '6'), ('-4 -2 5', '-6'), ('1 3 5', '0'), ('0', '0')),
         hints=_hints('Чётность относится к значению или к позиции элемента?', 'Juftlik element qiymatiga tegishlimi yoki uning o‘rnigami?',
                      'Берите значения с нулевым остатком от деления на 2, включая отрицательные.', '2 ga bo‘lgandagi qoldig‘i nol bo‘lgan qiymatlarni, jumladan manfiylarni oling.',
                      'Начните сумму с нуля и прибавляйте только элементы, для которых number % 2 == 0.', 'Yig‘indini noldan boshlang va faqat number % 2 == 0 shartiga mos elementlarni qo‘shing.'),
         py='numbers = list(map(int, input().split()))\nprint(sum(number for number in numbers if number % 2 == 0))',
         js='const numbers = prompt().trim().split(/\\s+/).map(Number);\nconsole.log(numbers.filter(number => number % 2 === 0).reduce((total, number) => total + number, 0));',
         change=text('Посчитайте количество чётных элементов вместо их суммы. Объясните разницу между счётчиком и суммой.',
                     'Juft elementlar yig‘indisi o‘rniga ularning sonini hisoblang. Hisoblagich va yig‘indi farqini tushuntiring.')),
    dict(key='one-divisor', category='logic', difficulty='intermediate',
         title=text('Ровно одно условие', 'Aynan bitta shart'),
         prompt=text('Дано целое число от 1 до 1000000. Выведите YES, если оно делится ровно на одно из чисел 3 и 5. Если делится на оба или ни на одно, выведите NO.',
                     '1 dan 1000000 gacha butun son berilgan. Son 3 va 5 dan aynan bittasiga bo‘linsa YES chiqaring. Ikkalasiga ham yoki hech biriga bo‘linmasa NO chiqaring.'),
         py_starter='number = int(input())\n# TODO\n', js_starter='const number = Number(prompt());\n// TODO\n',
         tests=_tests(('9', 'YES'), ('10', 'YES'), ('15', 'NO'), ('7', 'NO')),
         hints=_hints('Подходит ли число 15? Почему?', '15 soni mos keladimi? Nega?',
                      'Ответ YES нужен только тогда, когда результаты двух проверок различаются.', 'YES javobi faqat ikki tekshiruv natijalari turlicha bo‘lganda kerak.',
                      'Сравните булевы результаты делимости на 3 и на 5 с помощью !=.', '3 va 5 ga bo‘linishning mantiqiy natijalarini != orqali solishtiring.'),
         py='number = int(input())\nprint("YES" if (number % 3 == 0) != (number % 5 == 0) else "NO")',
         js='const number = Number(prompt());\nconsole.log((number % 3 === 0) !== (number % 5 === 0) ? "YES" : "NO");',
         change=text('Теперь выведите YES, только если число делится и на 3, и на 5. Объясните, какой логический оператор нужен.',
                     'Endi son 3 ga ham, 5 ga ham bo‘linsa YES chiqaring. Qaysi mantiqiy operator kerakligini tushuntiring.')),
    dict(key='board-color', category='logic', difficulty='intermediate',
         title=text('Цвет двух клеток', 'Ikki katak rangi'),
         prompt=text('Даны координаты двух клеток доски 8 × 8: x1, y1, x2, y2, каждое число от 1 до 8 на отдельной строке. Соседние по стороне клетки имеют разные цвета. Выведите YES, если цвета выбранных клеток одинаковы, иначе NO.',
                     '8 × 8 doskadagi ikki katak koordinatalari x1, y1, x2, y2 berilgan. Har bir son 1 dan 8 gacha, alohida qatorda. Tomoni bilan qo‘shni kataklar turli rangda. Tanlangan kataklar rangi bir xil bo‘lsa YES, aks holda NO chiqaring.'),
         py_starter='x1 = int(input())\ny1 = int(input())\nx2 = int(input())\ny2 = int(input())\n# TODO\n',
         js_starter='const x1 = Number(prompt());\nconst y1 = Number(prompt());\nconst x2 = Number(prompt());\nconst y2 = Number(prompt());\n// TODO\n',
         tests=_tests(('1\n1\n8\n8', 'YES'), ('1\n1\n1\n2', 'NO'), ('2\n3\n4\n5', 'YES'), ('8\n8\n8\n8', 'YES')),
         hints=_hints('Что меняется в сумме координат при переходе к соседней клетке?', 'Qo‘shni katakka o‘tganda koordinatalar yig‘indisi qanday o‘zgaradi?',
                      'Цвет можно связать с чётностью суммы x + y.', 'Rangni x + y yig‘indisining juftligi bilan bog‘lash mumkin.',
                      'Сравните остатки от деления (x1 + y1) и (x2 + y2) на 2.', '(x1 + y1) va (x2 + y2) yig‘indilarining 2 ga bo‘lish qoldiqlarini solishtiring.'),
         py='x1 = int(input())\ny1 = int(input())\nx2 = int(input())\ny2 = int(input())\nprint("YES" if (x1 + y1) % 2 == (x2 + y2) % 2 else "NO")',
         js='const x1 = Number(prompt());\nconst y1 = Number(prompt());\nconst x2 = Number(prompt());\nconst y2 = Number(prompt());\nconsole.log((x1 + y1) % 2 === (x2 + y2) % 2 ? "YES" : "NO");',
         change=text('Определите, стоят ли клетки на одной диагонали, и выведите YES или NO. Объясните связь разностей координат.',
                     'Kataklar bitta diagonalda joylashganini aniqlab, YES yoki NO chiqaring. Koordinatalar ayirmalari bog‘lanishini tushuntiring.')),
    dict(key='triangle', category='logic', difficulty='intermediate',
         title=text('Можно ли собрать треугольник', 'Uchburchak yasash mumkinmi'),
         prompt=text('Даны длины трёх отрезков — положительные целые числа не больше 100000, по одному на строке. Выведите YES, если из них можно составить невырожденный треугольник, иначе NO. Сумма любых двух сторон должна быть строго больше третьей.',
                     'Uchta kesma uzunligi berilgan: 100000 dan katta bo‘lmagan musbat butun sonlar, har biri alohida qatorda. Ulardan yuzasi musbat uchburchak yasash mumkin bo‘lsa YES, aks holda NO chiqaring. Istalgan ikki tomon yig‘indisi uchinchi tomondan qat’iy katta bo‘lishi kerak.'),
         py_starter='a = int(input())\nb = int(input())\nc = int(input())\n# TODO\n',
         js_starter='const a = Number(prompt());\nconst b = Number(prompt());\nconst c = Number(prompt());\n// TODO\n',
         tests=_tests(('3\n4\n5', 'YES'), ('1\n1\n2', 'NO'), ('9\n4\n3', 'NO'), ('2\n2\n2', 'YES')),
         hints=_hints('Что произойдёт, если одна сторона равна сумме двух других?', 'Bir tomon qolgan ikkitasining yig‘indisiga teng bo‘lsa nima bo‘ladi?',
                      'Равенство не подходит: нужен треугольник с положительной площадью.', 'Tenglik mos kelmaydi: yuzasi musbat uchburchak kerak.',
                      'Проверьте все три строгих неравенства и соедините их оператором and / &&.', 'Uchala qat’iy tengsizlikni tekshiring va ularni and / && operatori bilan birlashtiring.'),
         py='a = int(input())\nb = int(input())\nc = int(input())\nprint("YES" if a + b > c and a + c > b and b + c > a else "NO")',
         js='const a = Number(prompt());\nconst b = Number(prompt());\nconst c = Number(prompt());\nconsole.log(a + b > c && a + c > b && b + c > a ? "YES" : "NO");',
         change=text('Если треугольник существует, дополнительно выведите его периметр во второй строке. Объясните, когда второй строки не должно быть.',
                     'Uchburchak mavjud bo‘lsa, ikkinchi qatorda perimetrini ham chiqaring. Qachon ikkinchi qator bo‘lmasligini tushuntiring.')),
]

for _topic in _NEW_TOPICS:
    for _language, _ext in [('Python', 'py'), ('JavaScript', 'js')]:
        _item = exercise(f"{_topic['key']}-{_ext}", _language, _topic['title'], _topic['prompt'],
                         _topic[f'{_ext}_starter'], _topic['tests'], _topic['hints'], _topic[_ext], _topic['change'])
        _metadata(_item, _topic['category'], _topic['difficulty'])
        if _item['id'] in TEMPLATES:
            raise ValueError('Duplicate exercise ID')
        TEMPLATES[_item['id']] = _item


# Re-export for clients that imported the original learning catalog module.
from learning_glossary import GLOSSARY
