import aiohttp
from bs4 import BeautifulSoup
import json
import asyncio
import logging

# Настройка логгера
logger = logging.getLogger(__name__)

async def get_team_code(session, team):
    search_url = f'https://page.lfl.ru/search?search={team.lower().replace(" ", "%20")}'
    try:
        async with session.get(search_url) as response:
            if response.status != 200:
                return []
            text = await response.text()

        soup = BeautifulSoup(text, 'lxml')
        data = soup.find_all('li', class_='style_searchItem__li__mziH_')
        codes_raw = []

        for item in data:
            try:
                href = item.find('a').get('href')
                code = ''.join(char for char in href if char.isdigit())
                codes_raw.append(code)
            except AttributeError:
                continue

        # Remove duplicates preserving order
        seen = set()
        codes = [code for code in codes_raw if not (code in seen or seen.add(code))]
        return codes
    except Exception as e:
        logger.error(f"Error getting team code: {e}")
        return []

async def get_schedule(team):
    schedules = []
    teams_found = []

    async with aiohttp.ClientSession() as session:
        codes = await get_team_code(session, team)

        # Создаем список задач для параллельного выполнения запросов к календарю
        tasks = []
        for code in codes:
            url = f'https://page.lfl.ru/matches-calendar/{code}?order=asc&currentDate=upcoming'
            tasks.append(fetch_calendar(session, url))

        results = await asyncio.gather(*tasks)

        for res in results:
            if res:
                teams_found.append(res['team_name'])
                schedules.append(res['matches'])

    return teams_found, schedules

async def fetch_calendar(session, url):
    try:
        async with session.get(url) as response:
            if response.status != 200:
                return None
            text = await response.text()

        soup = BeautifulSoup(text, 'lxml')
        script_tag = soup.find('script', {'id': '__NEXT_DATA__'})

        if not script_tag:
            return None

        json_data = json.loads(script_tag.string)

        try:
            club_name = json_data['props']['pageProps']['club']['name']
            matches_data = json_data['props']['pageProps']['matches']

            if matches_data is None:
                return {'team_name': club_name, 'matches': 'На сайте расписания нет.'}

            data_list = matches_data.get('data', [])
            length = matches_data.get('length', 0)

            parsed_matches = []

            # Берем до 2 матчей
            limit = min(length, 2)
            for i in range(limit):
                match = data_list[i]
                parsed_matches.append({
                    "match_date_time": match['match_date_time'],
                    "stadium_name": match['stadium_name'],
                    "stadium_address": match['stadium_address'],
                    "home_club_name": match['home_club_name'],
                    "away_club_name": match['away_club_name'],
                })

            if not parsed_matches:
                return {'team_name': club_name, 'matches': 'На сайте расписания нет.'}

            return {'team_name': club_name, 'matches': parsed_matches}

        except (KeyError, TypeError, IndexError) as e:
            return None

    except Exception as e:
        logger.error(f"Error fetching calendar: {e}")
        return None