:- encoding(utf8).

% Лабораторная №2. Учебная база, НЕ текущий прогноз погоды.
% weather(Город, Температура_в_C, Состояние, Ветер_в_м_с).
% Ветер в Казани и Екатеринбурге выбран для учебного примера.
weather('Москва', 5, дождь, 7).
weather('Санкт-Петербург', 2, снег, 12).
weather('Казань', -3, снег, 4).
weather('Екатеринбург', -15, снег, 11).

% Непересекающиеся интервалы: [-10,0), [0,10), [10,20).
temp_advice(Temp, 'Очень холодно, одевайтесь максимально тепло!') :-
    number(Temp), Temp < -10.
temp_advice(Temp, 'Холодно, наденьте тёплую куртку и шапку.') :-
    number(Temp), Temp >= -10, Temp < 0.
temp_advice(Temp, 'Прохладно, возьмите ветровку или легкую куртку.') :-
    number(Temp), Temp >= 0, Temp < 10.
temp_advice(Temp, 'Тепло, можно гулять в джемпере или рубашке.') :-
    number(Temp), Temp >= 10, Temp < 20.
temp_advice(Temp, 'Жарко, лучше надеть футболку и шорты.') :-
    number(Temp), Temp >= 20.

cond_advice(дождь, 'Возьмите зонт, ожидается дождь.').
cond_advice(снег, 'Осторожно, снегопад, будьте аккуратны на дорогах.').
cond_advice(солнечно, 'Не забудьте солнечные очки и головной убор!').
cond_advice(облачно, 'Погода облачная, осадков не ожидается.').

% Ровно 10 м/с относится к среднему ветру, а не к сильному.
% Отрицательная скорость недопустима: такой запрос возвращает false.
wind_advice(Wind, 'Сильный ветер, будьте осторожны!') :-
    number(Wind), Wind > 10.
wind_advice(Wind, 'Ветрено, застегните куртку.') :-
    number(Wind), Wind >= 5, Wind =< 10.
wind_advice(Wind, 'Ветер слабый, комфортно.') :-
    number(Wind), Wind >= 0, Wind < 5.

% Входной режим: известны числовая температура и состояние.
% if-then-else обеспечивает ОДНУ рекомендацию, включая общий случай.
activity_advice(Temp, Cond, Activity) :-
    number(Temp),
    cond_advice(Cond, _),
    ( Temp > 20, Cond == солнечно ->
        Activity = 'Идеально для пляжа!'
    ; Temp >= 15, Temp =< 25, Cond == дождь ->
        Activity = 'Можно посетить музей или кафе.'
    ; Temp < 0, Cond == снег ->
        Activity = 'Хорошая погода для катания на лыжах.'
    ; Activity = 'Можно просто погулять по городу.'
    ).

% Части совета сохраняются отдельно: это помогает объяснить вывод.
advice_parts(City, [TempPart, CondPart, WindPart, Activity]) :-
    weather(City, Temp, Cond, Wind),
    temp_advice(Temp, TempPart),
    cond_advice(Cond, CondPart),
    wind_advice(Wind, WindPart),
    activity_advice(Temp, Cond, Activity).

advice_for(City, FullAdvice) :-
    advice_parts(City, Parts),
    atomic_list_concat(Parts, ' ', FullAdvice).

show_all_advices :-
    forall(advice_for(City, Advice),
           format('~w: ~w~n~n', [City, Advice])).

% ВАЖНО: правила дословно следуют учебному заданию.
% Они не оценивают безопасность прогулки/лыж при морозе и сильном ветре.
