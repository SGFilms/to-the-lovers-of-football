import requests
from bs4 import BeautifulSoup
import json


def get_team_code(team):
    search_url = f'https://page.lfl.ru/search?search={team.lower().replace(" ", "%20")}'
    response = requests.get(search_url)
    soup = BeautifulSoup(response.text, 'lxml')
    data = soup.find_all('li', class_='style_searchItem__li__mziH_')
    codes_raw = []

    # Extract numeric codes from hrefs
    for item in data:
        href = item.find('a').get('href')
        code = ''.join(char for char in href if char.isdigit())
        codes_raw.append(code)

    # Remove duplicates while preserving order
    seen = set()
    codes = [code for code in codes_raw if not (code in seen or seen.add(code))]

    return codes

def get_schedule(team):
    schedules = []
    codes = get_team_code(team)
    teams_found = []
    for code in codes:
        error_occurred = False
        calendar_url = f'https://page.lfl.ru/matches-calendar/{code}?order=asc&currentDate=upcoming'
        response = requests.get(calendar_url)
        soup = BeautifulSoup(response.text, 'lxml')
        script_tag = soup.find('script', {'id': '__NEXT_DATA__'})
        json_data = json.loads(script_tag.string)
        try:
            if json_data['props']['pageProps']['matches'] is None:
                error_occurred = True

            elif json_data['props']['pageProps']['matches']['length'] == 1:
                first_two_matches = [{
                    "match_date_time": json_data['props']['pageProps']['matches']['data'][0]['match_date_time'],
                    "stadium_name": json_data['props']['pageProps']['matches']['data'][0]['stadium_name'],
                    "stadium_address": json_data['props']['pageProps']['matches']['data'][0]['stadium_address'],
                    "home_club_name": json_data['props']['pageProps']['matches']['data'][0]['home_club_name'],
                    "away_club_name": json_data['props']['pageProps']['matches']['data'][0]['away_club_name'],
                }]
                schedules.append(first_two_matches)
                teams_found.append(json_data['props']['pageProps']['club']['name'])

            elif json_data['props']['pageProps']['matches']['length'] > 1:
                first_two_matches = [{
                    "match_date_time": json_data['props']['pageProps']['matches']['data'][0]['match_date_time'],
                    "stadium_name": json_data['props']['pageProps']['matches']['data'][0]['stadium_name'],
                    "stadium_address": json_data['props']['pageProps']['matches']['data'][0]['stadium_address'],
                    "home_club_name": json_data['props']['pageProps']['matches']['data'][0]['home_club_name'],
                    "away_club_name": json_data['props']['pageProps']['matches']['data'][0]['away_club_name'],
                }, {
                    "match_date_time": json_data['props']['pageProps']['matches']['data'][1]['match_date_time'],
                    "stadium_name": json_data['props']['pageProps']['matches']['data'][1]['stadium_name'],
                    "stadium_address": json_data['props']['pageProps']['matches']['data'][1]['stadium_address'],
                    "home_club_name": json_data['props']['pageProps']['matches']['data'][1]['home_club_name'],
                    "away_club_name": json_data['props']['pageProps']['matches']['data'][1]['away_club_name'],
                }]
                schedules.append(first_two_matches)
                teams_found.append(json_data['props']['pageProps']['club']['name'])
        except (RuntimeError, TypeError, NameError, KeyError, ValueError, IndexError, AttributeError):
            error_occurred = True

        if error_occurred:
            continue


    return teams_found, schedules


