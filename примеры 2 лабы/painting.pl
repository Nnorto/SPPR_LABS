:- encoding(utf8).

% Вводный пример из PDF. Цена указана за квадратный метр.
colour_cost(red, 1000).
colour_cost(white, 1030).
colour_cost(blue, 1070).

colouring_cost(Height, Width, Colour, Cost) :-
    number(Height), number(Width),
    Height >= 0, Width >= 0,
    colour_cost(Colour, ColourCost),
    Square is Height * Width,
    Cost is Square * ColourCost.
