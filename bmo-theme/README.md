# Тема BMO (Бимо) для Flipper Zero

Мордочки BMO из «Время приключений» для главного экрана Flipper: 9 анимаций, монохром 128×64,
движения сверены с тем, как Бимо ведёт себя в мультфильме.

## Установка

1. Скопировать папку `BMO_Faces` в `SD/asset_packs/` на карте Flipper.
2. На приборе: Настройки Momentum → Интерфейс → Графика → Тема (Asset Pack) → **BMO_Faces**.

Темы (asset packs) поддерживает Momentum; на официальной прошивке Flipper этой системы нет.

## Анимации

BMO_happy, BMO_laugh, BMO_smile, BMO_smirk, BMO_hmm, BMO_hng, BMO_oo, BMO_yawn, BMO_angy —
какая мордочка при каком настроении питомца, задаёт `BMO_Faces/Anims/manifest.txt`.

## Исходники

`source/` — исходные картинки (`BMO_source_png/`) и скрипты-генераторы
(`make_bmo_anims.py`, `make_bmo_passport.py`): можно перерисовать кадры и собрать заново.
Нужен Python 3 с `pillow`.

**Тема авторская** — все мордочки и портреты нарисованы с нуля специально для этого проекта,
не взяты из других наборов. BMO — персонаж «Adventure Time» (Cartoon Network);
тема фанатская, некоммерческая.
