:- encoding(utf8).
:- ensure_loaded(weather).
:- ensure_loaded(violations).
:- use_module(library(plunit)).

:- begin_tests(weather).
test(four_cities) :-
    findall(C, weather(C, _, _, _), Cities), length(Cities, 4).
test(ekaterinburg) :-
    weather('Екатеринбург', -15, снег, 11).
test(temp_below_minus_10) :-
    findall(A, temp_advice(-10.1, A),
            ['Очень холодно, одевайтесь максимально тепло!']).
test(temp_minus_10) :-
    findall(A, temp_advice(-10, A),
            ['Холодно, наденьте тёплую куртку и шапку.']).
test(temp_zero) :-
    findall(A, temp_advice(0, A),
            ['Прохладно, возьмите ветровку или легкую куртку.']).
test(temp_ten) :-
    findall(A, temp_advice(10, A),
            ['Тепло, можно гулять в джемпере или рубашке.']).
test(temp_twenty) :-
    findall(A, temp_advice(20, A),
            ['Жарко, лучше надеть футболку и шорты.']).
test(wind_zero) :-
    findall(A, wind_advice(0, A), ['Ветер слабый, комфортно.']).
test(wind_below_five) :-
    findall(A, wind_advice(4.9, A), ['Ветер слабый, комфортно.']).
test(wind_five) :-
    findall(A, wind_advice(5, A), ['Ветрено, застегните куртку.']).
test(wind_ten) :-
    findall(A, wind_advice(10, A), ['Ветрено, застегните куртку.']).
test(wind_above_ten) :-
    findall(A, wind_advice(10.1, A), ['Сильный ветер, будьте осторожны!']).
test(negative_wind, [fail]) :- wind_advice(-1, _).
test(beach) :-
    findall(A, activity_advice(21, солнечно, A), ['Идеально для пляжа!']).
test(not_beach_at_twenty) :-
    findall(A, activity_advice(20, солнечно, A),
            ['Можно просто погулять по городу.']).
test(museum_lower) :-
    findall(A, activity_advice(15, дождь, A), ['Можно посетить музей или кафе.']).
test(museum_upper) :-
    findall(A, activity_advice(25, дождь, A), ['Можно посетить музей или кафе.']).
test(rain_below_range) :-
    findall(A, activity_advice(14.9, дождь, A),
            ['Можно просто погулять по городу.']).
test(rain_above_range) :-
    findall(A, activity_advice(25.1, дождь, A),
            ['Можно просто погулять по городу.']).
test(skiing) :-
    findall(A, activity_advice(-1, снег, A),
            ['Хорошая погода для катания на лыжах.']).
test(no_skiing_at_zero) :-
    findall(A, activity_advice(0, снег, A),
            ['Можно просто погулять по городу.']).
test(unknown_condition, [fail]) :- activity_advice(5, туман, _).
test(unknown_city, [fail]) :- advice_for('Неизвестный город', _).
test(single_advice_per_city) :-
    forall(weather(C, _, _, _), (findall(A, advice_for(C, A), L), length(L, 1))).
test(four_advice_parts) :-
    forall(weather(C, _, _, _), (once(advice_parts(C, P)), length(P, 4))).
:- end_tests(weather).

:- begin_tests(violations).
test(three) :- findall(N, violation_count('А123АА116', N), [3]).
test(two) :- findall(N, violation_count('В456ВВ116', N), [2]).
test(zero) :- findall(N, violation_count('Е789ЕЕ116', N), [0]).
test(unknown, [fail]) :- violation_count('НЕИЗВЕСТНО', _).
test(enumeration) :-
    findall(P-N, violation_count(P, N),
            ['А123АА116'-3, 'В456ВВ116'-2, 'Е789ЕЕ116'-0]).
test(unique_ids) :-
    findall(I, violation(I, _, _, _), IDs),
    sort(IDs, Unique), length(IDs, N), length(Unique, N).
:- end_tests(violations).
