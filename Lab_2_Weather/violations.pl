:- encoding(utf8).

% Проект №4: подсчёт нарушений для автомобиля.
% Все номера, владельцы и события вымышлены.
% car(Номер, Владелец).
car('А123АА116', 'Иван Петров').
car('В456ВВ116', 'Анна Сидорова').
car('Е789ЕЕ116', 'Олег Иванов').

violation_type(speeding, 'Превышение скорости').
violation_type(parking, 'Нарушение правил парковки').
violation_type(red_light, 'Проезд на запрещающий сигнал').

% violation(ID, Номер, Тип, Дата).
% Разные ID обозначают разные события, даже с одинаковым типом.
violation(1, 'А123АА116', speeding, date(2026, 9, 1)).
violation(2, 'А123АА116', parking, date(2026, 9, 2)).
violation(3, 'А123АА116', speeding, date(2026, 9, 3)).
violation(4, 'В456ВВ116', red_light, date(2026, 9, 4)).
violation(5, 'В456ВВ116', parking, date(2026, 9, 5)).

% car/2 позволяет перечислять известные машины и отличает неизвестную
% машину (false) от известной без нарушений (Count = 0).
violation_count(Plate, Count) :-
    car(Plate, _),
    findall(ID, violation(ID, Plate, _, _), IDs),
    length(IDs, Count).

show_violation_counts :-
    forall(violation_count(Plate, Count),
           format('~w: ~d~n', [Plate, Count])).
