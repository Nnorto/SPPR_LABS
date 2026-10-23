:- encoding(utf8).
:- ensure_loaded(weather).
:- ensure_loaded(violations).

demo :-
    set_stream(user_output, encoding(utf8)),
    writeln('ЛАБОРАТОРНАЯ №2. УЧЕБНЫЕ ДАННЫЕ'),
    show_all_advices,
    writeln('Границы ветра:'),
    forall(member(W, [0, 4.9, 5, 10, 10.1]),
           (wind_advice(W, A), format('~w м/с: ~w~n', [W, A]))),
    nl, writeln('Активности:'),
    forall(member(T-C, [21-солнечно, 15-дождь, 25-дождь, -1-снег, 0-снег]),
           (activity_advice(T, C, A),
            format('~w C, ~w: ~w~n', [T, C, A]))),
    nl, writeln('Проект №4. Число нарушений:'),
    show_violation_counts.
