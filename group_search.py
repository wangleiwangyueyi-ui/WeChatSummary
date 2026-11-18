"""Shared matching for the daily and history group pickers."""
import calendar
import unicodedata


def normalize_name(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return ''.join(char for char in value
                   if not char.isspace() and unicodedata.category(char) != 'Cf')


def group_catalog(people):
    groups, aliases = {}, {}
    for uid, row in people.items():
        if not uid.endswith('@chatroom'):
            continue
        names = list(dict.fromkeys(str(row[key]) for key in ('remark', 'nick_name', 'alias')
                                   if row.get(key)))
        groups[uid] = names[0] if names else uid
        aliases[uid] = names
    return groups, aliases


def matching_groups(groups, aliases, query):
    terms = [normalize_name(word) for word in query.split()]
    terms = [word for word in terms if word]
    matches = []
    for uid, name in groups.items():
        fields = [normalize_name(value) for value in [uid, name, *aliases.get(uid, [])]]
        if all(any(term in field for field in fields) for term in terms):
            matches.append((uid, name))
    return sorted(matches, key=lambda item: (normalize_name(item[1]), item[0]))


def month_before(value):
    year, month = (value.year - 1, 12) if value.month == 1 else (value.year, value.month - 1)
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)
