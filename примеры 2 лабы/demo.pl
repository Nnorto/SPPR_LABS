:- encoding(utf8).
:- ensure_loaded(painting).
:- ensure_loaded(family).

demo :-
    set_stream(user_output, encoding(utf8)),
    writeln('ЛАБОРАТОРНАЯ №3. ПОКРАСКА И БАЗА ЗНАНИЙ'),
    nl, writeln('Все цены:'),
    forall(colour_cost(C, P), format('~w: ~w~n', [C, P])),
    nl, writeln('Цена за м2 ниже 1050:'),
    forall((colour_cost(C, P), P < 1050), format('~w: ~w~n', [C, P])),
    nl, writeln('Покраска 10 x 5:'),
    forall(colouring_cost(10, 5, C, Cost),
           format('~w: ~w~n', [C, Cost])),
    nl, writeln('Покраска 10 x 5 дешевле 52000:'),
    forall((colouring_cost(10, 5, C, Cost), Cost < 52000),
           format('~w: ~w~n', [C, Cost])),
    nl, writeln('Белая покраска 3 x 4:'),
    colouring_cost(3, 4, white, WhiteCost), writeln(WhiteCost),
    nl, writeln('Родители Ивана:'),
    parents_of('Иван', Parents), writeln(Parents),
    nl, writeln('Все родители и дети:'), show_pairs,
    nl, writeln('Внуки Ильи:'),
    forall(grandparent('Илья', Child), writeln(Child)),
    all_people(People), length(People, N),
    nl, format('Уникальных людей: ~d~n', [N]).
