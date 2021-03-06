#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import datetime
import logging
import re
import sys
from time import sleep
from collections import OrderedDict, namedtuple

import requests # pip install requests
from num2words import num2words as n2w # pip install num2words
from functools import lru_cache
from titlecase import titlecase # pip install titlecase
from jinja2 import Environment, FileSystemLoader, BaseLoader # pip install Jinja2

from Stat import Stat
from util import mail
try:
    from extra_stats import compute_extra_categories # see extra_stats.py.example for what this file should look like
except ImportError:
    compute_extra_categories = lambda data: ({}, [], data)

from util import exec_mysql, cm
from secrets import dbconfig, api_key

cm.set_credentials(dbconfig)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(message)s",
                    datefmt="%H:%M:%S")
logging.getLogger("requests").setLevel(logging.WARNING)

s = requests.Session()
s.headers.update({'AS-Key': api_key})

def num2words(n):
    if n < 10:
        return n2w(n, lang='en').title()
    return str(n)

def abbreviations(word, **kwargs):
    if word.upper() in ('AP', 'MU', 'NL'):
        return word.upper()

def get_stats(group_id, time_span='now', number=10, submitters=[0]):
    time_span = {'all time': 'now',
                 'monthly': 'month',
                 'weekly': 'week'}.get(time_span, time_span)
    output = {}
    logging.info('read table: group {}, span {}'.format(groups()[group_id], time_span))

    data = list(read_table(group_id, time_span))

    extra_definitions, extra_categories, data = compute_extra_categories(data)

    # these definitions are just for reference. if a category is to be active in a template it needs to be in this dictionary first
    definitions = {'ap': '',
                   'lifetime_ap': '(Total AP Across Recursions)',
                   'recursions': '',
                   'explorer': '(New Portals Visited)',
                   'discoverer': '(Portals Discovered)',
                   'seer': '(Seer Points)',
                   'recon': '(OPR Agreements)',
                   'trekker': '(Distance Walked)',
                   'builder': '(Resonators Deployed)',
                   'connector': '(Links Created)',
                   'mind-controller': '(Control Fields Created)',
                   'illuminator': '(Mind Units Captured)',
                   'recharger': '(XM Recharged)',
                   'liberator': '(Portals Captured)',
                   'pioneer': '(New Portals Captured)',
                   'engineer': '(Mods Deployed)',
                   'purifier': '(Resonators Destroyed)',
                   'specops': '(New Missions Completed)',
                   'missionday': '(Mission Days Attended)',
                   'nl-1331-meetups': '(NL-1331 Meetup(s) Attended)',
                   'cassandra-neutralizer': '(Unique Portals Neutralized)',
                   'hacker': '(Hacks)',
                   'translator': '(Glyph Hack Points)',
                   'sojourner': '(Longest Hacking Streak)',
                   'recruiter': '(Agents successfully recruited)',
                   'magnusbuilder': '(Unique Resonator Slots Deployed)',
                   'collector': '(XM Collected)',
                   'binder': '(Longest Link Ever Created)',
                   'country-master': '(Largest Control Field)',
                   'neutralizer': '(Portals Neutralized)',
                   'disruptor': '(Enemy Links Destroyed)',
                   'salvator': '(Enemy Control Fields Destroyed)',
                   'smuggler': '(Max Time Link Maintained)',
                   'link-master': '(Max Link Length × Days)',
                   'controller': '(Max Time Field Held)',
                   'field-master': '(Largest Field MUs × Days)',
                   'missionday':'(Mission Days Attended)'}
    definitions.update(extra_definitions)

    categories = list(definitions.keys()) + extra_categories
    submitters[0] = 0
    for category in categories:
        output[category] = {'scores': [], 'title': {'category': 'Top ' + titlecase(category.replace('_', ' '), callback=abbreviations), 'description': definitions.get(category.lower(), '')}}
        top_list = sorted((line for line in data if 0 < float(line[category])), key=lambda k: float(k[category]), reverse=True)
        submitters[0] = max(submitters[0], len(top_list))
        i = -1
        for i, line in enumerate(top_list):
            datum = float(line[category])
            if i > number-1 and datum != prev_datum: # the 0s got filtered out on that inscrutable line above
                break

            if datum >= 1000000:
                datum_string = '{:,}'.format(int(datum))
            else:
                datum_string = '{:,g}'.format(datum)

            output[category]['scores'].append('{}  {}'.format(line['name'], datum_string))
            prev_datum = datum
        if i < 0:
            del output[category]
    return output

def cleanup_data(data):
    last_submit = data['last_submit']
    for k, v in data.items():
        if v == '-':
            data[k] = 0
    data['last_submit'] = last_submit
    return data

def read_table(group_id, time_span):
    count = 0
    API_url = 'https://api.agent-stats.com/groups/{}/{}'
    r = s.get(API_url.format(group_id, time_span), stream=True)
    r.raise_for_status()
    for agent, data in r.json().items():
        data['name'] = '@'+agent
        count += 1
        yield cleanup_data(data)
    logging.info('%s rows' % count)

@lru_cache(maxsize=None)
def groups():
    r = s.get('https://api.agent-stats.com/groups', stream=True)
    r.raise_for_status()
    return dict([(g['groupid'], g['groupname']) for g in r.json() if '.' in g['groupid']])

def get_groups(group=None):
    if group in ('smurfs', 'frogs', 'all', None):
        group_id, group_name = None, None
    elif re.fullmatch(r'([0-9a-f]{14}\.[\d]{8})', group):
        group_id = group
        group_name = groups()[group]
    else:
        group_id = exec_mysql('SELECT url FROM groups WHERE `name` = "{}"'.format(group))[0][0]
        group_name = group

    return group_id, group_name

def test_new_badges(group):
    # leftover test function that will need to be moved elsewhere later, but for now it stays so i can test the inevitable bugs introduced last time
    from colorama import init, Fore, Back, Style # pip install colorama
    init() # colorama
    from pprint import pprint

    def red(s):
        return Style.BRIGHT + Back.RED + str(s) + Style.RESET_ALL
    def yellow(s):
        return Back.YELLOW + Fore.BLACK + str(s) + Style.RESET_ALL
    def green(s):
        return Style.BRIGHT + Back.GREEN + str(s) + Style.RESET_ALL


    inputs = OrderedDict([
              ('same', ['Bronze', 'Bronze']),
              ('one standard rank', ['Bronze', 'Silver']),
              ('multi standard ranks', ['Bronze', 'Gold']),
              ('same extended ranks', ['4x Onyx', '4x Onyx']),
              ('one extended rank', ['4x Onyx', '5x Onyx']),
              ('multi extended ranks', ['4x Onyx', '7x Onyx']),
              ('one standard to one extended', ['Onyx', '2x Onyx']),
              ('multi standard to one extended', ['Gold', '2x Onyx']),
              ('one standard to multi extended', ['Onyx', '3x Onyx']),
              ('multi standard to multi extended', ['Gold', '4x Onyx']),
              ('locked same', ['Locked', 'Locked']),
              ('locked one standard rank', ['Locked', 'Bronze']),
              ('locked multi standard ranks', ['Locked', 'Gold']),
              ('locked multi standard to one extended', ['Locked', '2x Onyx']),
              ('backwards standard', ['Onyx', 'Locked']),
              ('backwards extended', ['5x Onyx', '2x Onyx']),
              ('backwards extended to standard', ['10x Onyx', 'Bronze']),
              ])

    old, new = [OrderedDict(zip(inputs,t)) for t in zip(*inputs.values())]

    expected = {
                'same': None,
                'one standard rank': ['Silver'],
                'multi standard ranks': ['Silver', 'Gold'],
                'same extended ranks': None,
                'one extended rank': ['5x Onyx'],
                'multi extended ranks': ['5x Onyx', '6x Onyx', '7x Onyx'],
                'one standard to one extended': ['2x Onyx'],
                'multi standard to one extended': ['Platinum', 'Onyx', '2x Onyx'],
                'one standard to multi extended': ['2x Onyx', '3x Onyx'],
                'multi standard to multi extended': ['Platinum', 'Onyx', '2x Onyx', '3x Onyx', '4x Onyx'],
                'locked same': None,
                'locked one standard rank': ['Bronze'],
                'locked multi standard ranks': ['Bronze', 'Silver', 'Gold'],
                'locked multi standard to one extended': ['Bronze', 'Silver', 'Gold', 'Platinum', 'Onyx', '2x Onyx'],
                'backwards standard': None,
                'backwards extended': None,
                'backwards extended to standard': None
               }

    result = new_badges(old, new)
    pprint(result)
    print('passed:', result == expected)

def new_badges(old_data, new_data):
    ranks = ['Locked', 'Bronze', 'Silver', 'Gold', 'Platinum', 'Onyx']

    result = OrderedDict()
    for category, old_rank in old_data.items():
        new_rank = new_data[category]
        #result[category] = None # only for testing. Do not send Nones down the pike
        if old_rank != new_rank:
            old, new = old_rank.split('x '), new_rank.split('x ')
            if not old[0].isdecimal():
                if not new[0].isdecimal():
                    if ranks.index(old[0]) < ranks.index(new[0]):
                        result[category] = ranks[ranks.index(old[0])+1:ranks.index(new[0])+1]
                else:
                    result[category] = ranks[ranks.index(old[0])+1:ranks.index(new[1])+1]

            if new[0].isdecimal():
                if old[0].isdecimal():
                    if int(old[0]) < int(new[0]):
                        result[category] = ['%sx %s' % (x, new[1]) for x in range(int(old[0])+1, int(new[0])+1)]
                else:
                    result[category].extend( ['%sx %s' % (x, new[1]) for x in range(2, int(new[0])+1)] )
    return result

def englishify(new_badges):
    data = []
    for badge, ranks in new_badges.items():
        onyx_ranks = []
        onyx_index = next((i for i, rank in enumerate(ranks) if 'Onyx' in rank), 'not found')
        if onyx_index != 'not found':
            ranks, onyx_ranks = ranks[:onyx_index], ranks[onyx_index:]  # split off all onyx variants
        if len(onyx_ranks) > 2:
            onyx_ranks = [onyx_ranks[0] + ' through ' + onyx_ranks[-1]] # shorten to single string
        ranks.extend(onyx_ranks)                                        # stick the onyx badges back on
        data.append(badge.upper() + ' ' + ', '.join(ranks[:-2] + [' and '.join(ranks[-2:])]))

    return ', '.join(data[:-2] + [' and '.join(data[-2:])])

def test(group):
    pass

def collate_agents():
    logging.info('collate agents')
    general_groups = dict(exec_mysql("SELECT name, idgroups FROM groups WHERE name IN ('smurfs', 'frogs', 'all');"))
    for agent_id, name, faction in exec_mysql('SELECT idagents, name, faction FROM agents;'):
        faction = 'frogs' if faction == 'enl' else 'smurfs'
        sql = '''INSERT INTO `membership`
                 VALUES ('{}', '{}')
                 ON DUPLICATE KEY UPDATE idagents=idagents;'''.format(agent_id, general_groups['all'])
        exec_mysql(sql)

        sql = '''INSERT INTO `membership`
                 VALUES ('{}', '{}')
                 ON DUPLICATE KEY UPDATE idagents=idagents;'''.format(agent_id, general_groups[faction])
        exec_mysql(sql)

def snarf(group=None):
    group_id, group_name = get_groups(group)

    if not group_id:
        results = ''
        for group_id, group_name in groups().items():
            logging.info('snarfing '+group_name)
            idgroups = exec_mysql("SELECT idgroups FROM groups WHERE url = '{}';".format(group_id))
            if not idgroups:
                sql = '''INSERT INTO `groups`
                         SET `name`='{}', url='{}';'''.format(group_name, group_id)
                exec_mysql(sql)
            results += snarf(group_id) # getting all recursive and shiz
        collate_agents()
        return results
    else:
        added, removed, flagged, flipped = [], [], [], []
        idgroups = exec_mysql("SELECT idgroups FROM groups WHERE url = '{}';".format(group_id))[0][0]
        remaining_roster = [item for sublist in exec_mysql("SELECT idagents FROM membership WHERE idgroups = {};".format(idgroups)) for item in sublist] # get the class attendance sheet

        logging.info('read table: group {}, span now'.format(group_name))
        for data in read_table(group_id, 'now'):
            stat = Stat()
            stat.table_load(**data)
            stat.save()
            if stat.flag and stat.changed:
                flagged.append((stat.date, stat.name, stat.reasons))

            try:
                remaining_roster.remove(stat.agent_id) # take attendance
            except ValueError:
                logging.info('Agent added: {} {}'.format(stat.faction.upper(), stat.name)) # new kid
                added.append(stat.faction.upper() + ' ' + stat.name)

            sql = '''INSERT INTO `membership`
                     VALUES ('{}', '{}')
                     ON DUPLICATE KEY UPDATE idagents=idagents;'''.format(stat.agent_id, idgroups)
            exec_mysql(sql)

            if stat.faction != exec_mysql('SELECT faction FROM agents WHERE `name` = "{}";'.format(stat.name))[0][0]:
                logging.info('Agent flipped: {} -> {}'.format(stat.name, stat.faction.upper()))
                flipped.append('{} -> {}'.format(stat.name, stat.faction))
                exec_mysql('UPDATE agents SET faction="{}" WHERE `name`="{}";'.format(stat.faction, stat.name))

        if remaining_roster:
            remaining_roster = str(tuple(remaining_roster)).replace(',)',')') # absentees
            removed = sum(exec_mysql("SELECT name FROM agents WHERE idagents in {};".format(remaining_roster)), ())
            logging.info('Agent(s) removed: %s' % str(removed))
            exec_mysql("DELETE FROM membership WHERE idagents in {} and idgroups = {};".format(remaining_roster, idgroups))

        output = []
        if added or removed or flagged or flipped:
            output.append(group_name+':')
            if flipped:
                output.append('  Flipped:')
                output.append('    '+'\n    '.join(flipped))

            if added:
                output.append('  Added:')
                output.append('    '+'\n    '.join(added))

            if removed:
                output.append('  Removed:')
                output.append('    '+'\n    '.join(removed))

            if flagged:
                output.append('  Flagged:')
                for flagged_agent in flagged:
                    output.append('    {} {}'.format(*flagged_agent))
                    output.append('      '+'\n      '.join(flagged_agent[2]))

        return '\n'.join(output) + '\n'

def get_badges(data):
    categories = {'explorer': [100, 1000, 2000, 10000, 30000],
                  'discoverer': [10, 50, 200, 500, 5000],
                  'seer': [10, 50, 200, 500, 5000],
                  'recon': [100, 750, 2500, 5000, 10000],
                  'trekker': [10, 100, 300, 1000, 2500],
                  'builder': [2000, 10000, 30000, 100000, 200000],
                  'connector': [50, 1000, 5000, 25000, 100000],
                  'mind_controller': [100, 500, 2000, 10000, 40000],
                  'illuminator': [5000, 50000, 250000, 1000000, 4000000],
                  'recharger': [100000, 1000000, 3000000, 10000000, 25000000],
                  'liberator': [100, 1000, 5000, 15000, 40000],
                  'pioneer': [20, 200, 1000, 5000, 20000],
                  'engineer': [150, 1500, 5000, 20000, 50000],
                  'purifier': [2000, 10000, 30000, 100000, 300000],
                  'specops': [5, 25, 100, 200, 500],
                  'missionday': [1, 3, 6, 10, 20],
                  'nl_1331_meetups': [1, 5, 10, 25, 50],
                  'hacker': [2000, 10000, 30000, 100000, 200000],
                  'translator': [200, 2000, 6000, 20000, 50000],
                  'sojourner': [15, 30, 60, 180, 360],
                  'recruiter': [2, 10, 25, 50, 100],
                  'recursions': [1, 1000001, 1000002, 1000003, 1000004]} # TODO: update this if it ever becomes a tiered badge

    result = {} # TODO: change these 2 dicts to OrderedDicts
    for category, ranks in categories.items():
        current = 'Locked'
        multiplier = 1
        for rank, badge in zip(ranks, ['Bronze', 'Silver', 'Gold', 'Platinum', 'Onyx']):
            if data[category] not in ['-', None] and int(data[category]) >= rank:
                current = badge
            if current == 'Onyx':
                multiplier = data[category] // rank
                if multiplier > 1:
                    current = '%sx %s' % (multiplier, current)
        result[category] = current

    for category, ranks in {'cassandra_neutralizer': [100, 300, 1000]}.items(): # doesn't strictly have to be a loop, but i want it to match above
        current = 'Locked'
        multiplier = 1
        for rank, badge in zip(ranks, ['Bronze', 'Silver', 'Gold']):
            if data[category] not in ['-', None] and int(data[category]) >= rank:
                current = badge
            if current == 'Gold': # highest rank
                multiplier = data[category] // rank
                if multiplier > 1:
                   current = '%sx %s' % (multiplier, current)
        result[category] = current

    return result

def summary(group='all', days=7):
    snarf(group)

    group_id, group_name = get_groups(group)
    if not group_id:
        group_id = {'all': 1, 'smurfs': 2, 'frogs':3}.get(group, None)

    headers = ('explorer',
               'discoverer',
               'seer',
               'recon',
               'trekker',
               'builder',
               'connector',
               'mind_controller',
               'illuminator',
               'recharger',
               'liberator',
               'pioneer',
               'engineer',
               'purifier',
               'specops',
               'missionday',
               'nl_1331_meetups',
               'cassandra_neutralizer',
               'hacker',
               'translator',
               'sojourner',
               'recruiter',
               'magnusbuilder',
               'recursions')

    sql_before = '''SELECT x.name, s.`date`, `level`, ap, explorer, discoverer, seer, recon, trekker, builder, connector, 
                           `mind-controller` mind_controller, illuminator, recharger, liberator, pioneer, engineer, purifier,
                           specops, missionday, `nl-1331-meetups` nl_1331_meetups, `cassandra-neutralizer` cassandra_neutralizer, hacker, translator, sojourner,
                           recruiter, magnusbuilder, recursions
                    FROM (
                        SELECT a.name name, s.idagents id, MAX(s.date) AS date
                        FROM agents a, stats s, membership m, groups g
                        WHERE a.idagents = s.idagents AND
                              s.idagents = m.idagents AND
                              m.idgroups = g.idgroups AND
                              g.`url` = '{}' AND
                              s.flag != 1 AND
                              date < ( CURDATE() - INTERVAL {} DAY )
                        GROUP BY id ) x
                    JOIN stats s ON x.id = s.idagents AND x.date = s.date
                 '''.format(group_id, days)

    baseline = {}
    for row in exec_mysql(sql_before):
        agent = row[0]
        if row[1]: # if has date. filters out the agents with rows of all 0s
            baseline[agent] = {'date': row[1], 'level': row[2], 'ap': row[3],
                               'badges': get_badges(dict(zip(headers, row[4:])))}

    sql_now = '''SELECT x.name, s.`date`, `level`, ap, explorer, discoverer, seer, recon, trekker, builder, connector,
                        `mind-controller` mind_controller, illuminator, recharger, liberator, pioneer, engineer, purifier,
                        specops, missionday, `nl-1331-meetups` nl_1331_meetups, `cassandra-neutralizer` cassandra_neutralizer, hacker, translator, sojourner,
                        recruiter, magnusbuilder, recursions
                    FROM (
                        SELECT a.name name, s.idagents id, MAX(s.date) AS date
                        FROM agents a, stats s, membership m, groups g
                        WHERE a.idagents = s.idagents AND
                              s.idagents = m.idagents AND
                              m.idgroups = g.idgroups AND
                              g.`url` = '{}' AND
                              s.flag != 1 AND
                              date >= ( CURDATE() - INTERVAL {} DAY )
                        GROUP BY id ) x
                    JOIN stats s ON x.id = s.idagents AND x.date = s.date
              '''.format(group_id, days)
    output = {'data': []}
    footnote = ''
    for row in exec_mysql(sql_now):
        agent = row[0]
        if agent in baseline:
            date_old = baseline[agent]['date']
            date_new = row[1]
            level_old = baseline[agent]['level']
            level_new = row[2]
            ap_old = baseline[agent]['ap']
            ap_new = row[3]
            ap_40m_old = int(ap_old)//40000000
            ap_40m_new = int(ap_new)//40000000
            badges_old = baseline[agent]['badges']
            badges_new = get_badges(dict(zip(headers, row[4:])))
            changes = OrderedDict()
            if badges_old != badges_new:
                changes.update(new_badges(badges_old, badges_new))
            if ap_40m_old < ap_40m_new:
                changes['ap'] = ['{} MILLION'.format((l+1)*40) for l in range(ap_40m_old, ap_40m_new)]
            if level_old < level_new:
                changes['level'] = [str(l+1) for l in range(level_old, level_new)]
            if changes:
                earnings = englishify(changes)
                today = datetime.date.today()
                stale = today - datetime.timedelta(days=days*2)
                note = ''
                if date_old < stale:
                    note = '¹' # chcp 65001
                    footnote = '¹Start date more than 2 %s ago' % ('weeks' if days == 7 else 'months',)

                if today.year == date_old.year:
                    template = 'earned {} sometime between {old.month}/{old.day}{} and {new.month}/{new.day}'
                else:
                    template = 'earned {} sometime between {old.month}/{old.day}/{old.year}{} and {new.month}/{new.day}/{new.year}'

                output['data'].append({'name': agent, 'earned': template.format(earnings, note, old=date_old, new=date_new)})
    output['data'] = sorted(output['data'], key=lambda s: s['name'].lower())
    if footnote:
        output['footnote'] = footnote
    return output

def weekly_roundup(group):
    group_id, group_name = get_groups(group)
    if not group_id: return 'please specify group'

    logging.info('starting weekly roundup')
    start = datetime.datetime.now()

    output_dict = {}
    submitters = [0] # this list gets modified inside get_stats()

    output_dict['week'] = (start - datetime.timedelta(days=7)).date().strftime("%m/%d")

    logging.info('getting weekly top lists')
    output_dict['chart'] = get_stats(group_id, 'weekly', args.number, submitters)

    logging.info('getting badge dings')
    output_dict['dings'] = summary(group_id, 7)

    output_dict['start'] = start
    output_dict['group_id'] = group_id
    output_dict['name'] = group_name

    output_dict['n'] = num2words(args.number).lower()
    output_dict['number'] = num2words(min(args.number, submitters[0]))
    output_dict['submitters'] = num2words(submitters[0])

    end = datetime.datetime.now()
    output_dict['duration'] = end-start

    return render(output_dict)

def monthly_roundup(group):
    group_id, group_name = get_groups(group)
    if not group_id: return 'please specify group'

    logging.info('starting monthly roundup')
    start = datetime.datetime.now()

    output_dict = {}
    submitters = [0] # this list gets modified inside get_stats()

    month = (start - datetime.timedelta(days=start.day)).date()
    output_dict['month'] = month.strftime("%B")
    
    logging.info('getting monthly top lists')
    output_dict['chart'] = get_stats(group_id, 'monthly', args.number, submitters)

    logging.info('getting badge dings')
    output_dict['dings'] = summary(group_id, month.day)
    
    output_dict['start'] = start
    output_dict['group_id'] = group_id
    output_dict['name'] = group_name
    
    output_dict['n'] = num2words(args.number).lower()
    output_dict['number'] = num2words(min(args.number, submitters[0]))
    output_dict['submitters'] = num2words(submitters[0])
    
    end = datetime.datetime.now()
    output_dict['duration'] = end-start
    
    return render(output_dict)

def custom_roundup(group):
    group_id, group_name = get_groups(group)
    if not group_id: return 'please specify group'

    logging.info('starting custom roundup')
    start = datetime.datetime.now()

    output_dict = {}
    submitters = [0] # this list gets modified inside get_stats()

    r = s.get('https://api.agent-stats.com/groups/{}/info'.format(group_id), stream=True)
    r.raise_for_status()
    startDate = datetime.datetime.strptime(r.json()['startDate'], '%Y-%m-%d %H:%M:%S')
    endDate = datetime.datetime.strptime(r.json()['endDate'], '%Y-%m-%d %H:%M:%S')
    output_dict['startDate'] = startDate
    output_dict['endDate'] = endDate

    try:
        lastRefresh = datetime.datetime.strptime(r.json()['lastRefresh'], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        lastRefresh = datetime.datetime.min
    if lastRefresh < endDate:
        logging.info('setting off a refresh. waiting 10 seconds to make sure it finishes')
        r = s.post('https://api.agent-stats.com/groups/{}/refresh'.format(group_id))
        r.raise_for_status()
        sleep(10)

    logging.info('getting custom top lists')
    output_dict['chart'] = get_stats(group_id, 'custom', args.number, submitters)

    logging.info('getting badge dings')
    output_dict['dings'] = summary(group_id, (endDate - startDate).days)
    
    output_dict['start'] = start
    output_dict['group_id'] = group_id
    output_dict['name'] = group_name
    
    output_dict['n'] = num2words(args.number).lower()
    output_dict['number'] = num2words(min(args.number, submitters[0]))
    output_dict['submitters'] = num2words(submitters[0])
    
    end = datetime.datetime.now()
    output_dict['duration'] = end-start

    return render(output_dict)

def render(output_dict):
    env = Environment(loader = FileSystemLoader('templates', followlinks=True))
    ext = '.' + args.extension
    if ext == '.debug':
        template = Environment(loader=BaseLoader()).from_string('{{output_dict|pprint}}')
        return template.render(output_dict=output_dict)
    template = env.get_or_select_template([output_dict['group_id']+ext, 'custom_template'+ext, 'template'+ext])
    return template.render(**output_dict)

def check_for_applicants(group):
    group_id, group_name = get_groups(group)
    r = s.get('https://api.agent-stats.com/groups/{}/pending'.format(group_id), stream=True)
    r.raise_for_status()
    message = []
    if r.json():
        message.append('Agent(s) awaiting validation to the {} group:'.format(group))
        for agent in r.json():
            message.append('    @{username}'.format(**dict(agent)))

        message.append('\nGo to https://www.agent-stats.com/groups.php?group={} and click on the [View admin panel] button to take care of it.'.format(group_id))
    return '\n'.join(message)

def update_group_names(group):
    db = dict(exec_mysql('SELECT url, `name` FROM groups WHERE url IS NOT NULL;'))
    web = dict(groups())
    allgood = True
    for gid in web:
        if web[gid] != db[gid]:
            allgood = False
            print('{} was named "{}" is now "{}"'.format(gid, db[gid], web[gid]))
            if input('Update the database? (y/N) ').lower().startswith('y'):
                exec_mysql('UPDATE groups SET `name`="{}" WHERE url="{}" AND `name`="{}"; '.format(web[gid], gid, db[gid]))
    if allgood:
        print('\nAll group names match\n')

if __name__ == '__main__':
    actions = OrderedDict([('snarf', snarf),
                           ('summary', summary),
                           ('weekly', weekly_roundup),
                           ('monthly', monthly_roundup),
                           ('custom', custom_roundup),
                           ('check_for_applicants', check_for_applicants),
                           ('update_group_names', update_group_names),
                           ('test', test)])

    parser = argparse.ArgumentParser(description='Tools for agent-stats admins')
    parser.add_argument('action', help='task to perform', choices=actions)
    parser.add_argument('-n', '--number', default=10, type=int, help='number of ranks to show')
    parser.add_argument('-g', '--group', help='group to focus on', choices=[name for row in exec_mysql('SELECT name FROM groups;') for name in row])
    parser.add_argument('-m', '--mail', nargs='*', help='email address to get output')
    parser.add_argument('-s', '--subject', help='optional email subject')
    parser.add_argument('-a', '--attach', action='store_true', help='also attach email body at a txt file to the email')
    parser.add_argument('-e', '--extension', default='txt', help='extension of template you want to use')

    args = parser.parse_args()

    try:
        result = actions.get(args.action)(args.group)
    except:
        if not args.mail:
            raise
        else:
            if not args.group: args.group=''
            subject = args.action+' '+args.group if not args.subject else args.subject
            mail([args.mail[0]], subject, str(sys.exc_info()[0]), host=True)
            logging.info('CRASHED and email sent')
    else:
        if result:
            result = result.strip()

            if not args.mail:
                print(result) # chcp 65001
            elif result:
                if not args.group: args.group=''
                subject = args.action+' '+args.group if not args.subject else args.subject
                mail(args.mail, subject, result, args.attach)
                logging.info('email sent')
        logging.info('Done')
