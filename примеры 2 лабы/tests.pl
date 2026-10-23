:- encoding(utf8).
:- ensure_loaded(painting).
:- ensure_loaded(family).
:- use_module(library(plunit)).

:- begin_tests(painting).
test(white_price) :- colour_cost(white, 1030).
test(blue_price) :- colour_cost(blue, 1070).
test(all_colours) :-
    findall(C-P, colour_cost(C, P), [red-1000, white-1030, blue-1070]).
test(cheap_paint) :-
    findall(C, (colour_cost(C, P), P < 1050), [red, white]).
test(red_surface) :- colouring_cost(10, 5, red, 50000).
test(white_surface) :- colouring_cost(3, 4, white, 12360).
test(all_surface_costs) :-
    findall(C-P, colouring_cost(10, 5, C, P),
            [red-50000, white-51500, blue-53500]).
test(budget) :-
    findall(C, (colouring_cost(10, 5, C, P), P < 52000), [red, white]).
test(negative_size, [fail]) :- colouring_cost(-1, 5, red, _).
test(zero_size) :- colouring_cost(0, 5, red, 0).
test(unknown_colour, [fail]) :- colouring_cost(1, 1, green, _).
:- end_tests(painting).

:- begin_tests(family).
test(ivan_parents) :- parents_of('Иван', ['Елена', 'Сергей']).
test(all_records) :- all_pairs(Pairs), length(Pairs, 9).
test(population) :- all_people(People), length(People, 12).
test(grandchildren) :-
    findall(C, grandparent('Илья', C), ['Ира', 'Саша']).
test(no_parents_in_database) :- parents_of('Неизвестный', []).
test(two_parents_for_sasha) :-
    parents_of('Саша', ['Марина', 'Николай']).
test(original_seven_preserved) :-
    forall(member(P-C, ['Илья'-'Марина', 'Марина'-'Ира',
           'Елена'-'Иван', 'Николай'-'Ира', 'Ольга'-'Алексей',
           'Марина'-'Саша', 'Сергей'-'Иван']), родитель(P, C)).
:- end_tests(family).
