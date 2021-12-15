# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Thomas Amland
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

import re
import xbmc
import json
import time
from datetime import datetime
from requests import Session

session = Session()
session.headers['User-Agent'] = 'kodi.tv'

def _get(path, params=''):
    api_key = 'd1381d92278a47c09066460f2522a67d'
    r = session.get('https://psapi.nrk.no{}?apiKey={}{}'.format(path, api_key, params))
    parsed = r.json()
    xbmc.log('NRK REQUEST: {}'.format(path).encode('utf-8'), xbmc.LOGDEBUG)
    #xbmc.log('NRK REQUEST: {} ->\n{}'.format(path, json.dumps(r.json(), indent=4)).encode('utf-8'), xbmc.LOGDEBUG)
    r.raise_for_status()
    return parsed

def _getDeep(obj, next_key, *remaining_keys):
    obj = obj.get(next_key)
    return _getDeep(obj, *remaining_keys) if obj and remaining_keys else obj


def _getImageUrlFromList(items, min_width=0):
    for image in items or []:
        if image.get('width', 0) >= min_width:
            xbmc.log('selected image: ' + str(image), xbmc.LOGDEBUG)
            return image.get('url') or image.get('uri')


def _image_url_key_standardize(images):
    xs = images
    for image in xs:
        image['url'] = image['imageUrl']
        del image['imageUrl']
    return xs


def _get_playback_url(manifest_url):
    playable = _get(manifest_url)['playable']
    if playable:
        return playable['assets'][0]['url']
    else:
        return None


class ImageMixin(object):
    thumbs = None
    posters = None
    backdrops = None


    @property
    def thumb(self):
        return _getImageUrlFromList(self.thumbs, min_width=400)

    @property
    def poster(self):
        return _getImageUrlFromList(self.posters, min_width=800)

    @property
    def fanart(self):
        return _getImageUrlFromList(self.backdrops, min_width=1920)


class Base(object):
    id = None
    title = None
    is_series = False

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class Category(ImageMixin, Base):

    @staticmethod
    def from_response(r):
        return Category(
            id=r.get('id'),
            title=r.get('title') or r.get('displayValue'),
            thumbs=_getDeep(r, 'image', 'webImages'),
            posters=_getDeep(r, 'mainCategoryImages', 'landscape', 'webImages'),
            backdrops=_getDeep(r, 'mainCategoryImages', 'landscape', 'webImages'),
        )


class Channel(ImageMixin, Base):
    manifest = None

    @staticmethod
    def from_response(r):
        return Channel(
            title=r['_embedded']['playback']['title'],
            id=r['id'],
            manifest=r['_links']['manifest']['href'],
            images=r['_embedded']['playback']['posters'][0]['image']['items'],
        )


class Series(ImageMixin, Base):
    is_series = True
    description = None
    legal_age = None
    available = True
    category = None
    ''':class:`Category`'''

    @staticmethod
    def from_response(r):
        category = Category.from_response(r['category']) if 'category' in r else None
        images = _image_url_key_standardize(r.get('image', {}).get('webImages', None))
        return Series(
            id=r['id'],
            title=r['title'].strip(),
            category=category,
            description=r.get('description'),
            legal_age=r.get('legalAge', {}).get('displayValue', '') or r.get('aldersgrense'),
            images=images,
            available=r.get('hasOndemandrights', True)
        )

class Season(Base):
    is_season = True
    ''':class:`Season`'''

    @staticmethod
    def from_response(r):
        return Season(
            id=r['name'],
            title=r.get('title', '').strip(),
        )


class Program(ImageMixin, Base):

    @staticmethod
    def from_id(program_id):
        return Program(
                id=program_id,
                _program_href='/programs/%s' % program_id,
                _playback_href='/playback/metadata/%s' % program_id,
                )

    @property
    def _program(self):
        if not hasattr(self, '_program_r'):
            self._program_r = _get(self._program_href)
        return self._program_r

    @property
    def _playback(self):
        if not hasattr(self, '_playback_r'):
            self._playback_r = _get(self._playback_href)
        return self._playback_r

    @property
    def title(self):
        return _getDeep(self._program, 'title')

    @property
    def subtitle(self):
        #return _getDeep(self._playback, 'preplay', 'titles', 'subtitle')
        pass


    @property
    def description(self):
        return _getDeep(self._program, 'shortDescription')

    @property
    def category(self):
        categoryObj = _getDeep(self._program, 'category')
        category = Category.from_response(categoryObj) if categoryObj else None

    @property
    def categories(self):
        return [Category.from_response(cat) for cat in
                self._program.get('categories')]

    @property
    def thumbs(self):
        return _getDeep(self._program, 'image', 'webImages')

    @property
    def posters(self):
        return _getDeep(self._playback, 'preplay', 'poster', 'images')

    @property
    def aired(self):
        try:
            aired_str = _getDeep(self._program,
                    'moreInformation', 'releaseDateOnDemand')[:19]
            return datetime(*(time.strptime(aired_str, "%Y-%m-%dT%H:%M:%S")[0:6]))
        except ValueError:
            return None

    @property
    def duration(self):
        return  _getDeep(self._program, 'moreInformation', 'duration', 'seconds')

    @property
    def legal_age(self):
        return _getDeep(self._playback, 'legalAge', 'body', 'rating', 'displayAge')


    @property
    def available(self):
        #return self._playback.get('playability') == 'playable'
        return _getDeep(self._program,
                'programInformation', 'availability', 'status') in [
                        'available', 'expires']

    @property
    def media_urls(self):
        manifests = _getDeep(self._playback, '_links', 'manifests')
        for link in manifests:
            url = _get_playback_url(link['href'])
            if url:
                return [url]


def recommended_programs(medium='tv', category_id=None):
    if category_id:
        url = '/medium/%s/categories/%s/recommendedprograms' % (medium, category_id)
    else:
        url = '/medium/%s/recommendedprograms' % medium

    response = _get(url, '&maxnumber=15')
    return len(response), (program(item['id']) for item in response)


def popular_programs(medium='tv', category_id=None, list_type='week'):
    if category_id:
        return [program(item['id']) for item in
                _get('/medium/%s/categories/%s/popularprograms' % (medium, category_id),
                     '&maxnumber=15')]
    else:
        return [program(item['id']) for item in
                _get('/medium/%s/popularprograms/%s' % (medium, list_type),
                     '&maxnumber=15')]


def recent_programs(medium='tv', category_id=None):
    if category_id:
        return [program(item['id']) for item in
                _get('/medium/%s/categories/%s/recentlysentprograms' % (medium, category_id),
                     '&maxnumber=15')]
    else:
        return [program(item['id']) for item in
                _get('/medium/%s/recentlysentprograms' % medium,
                     '&maxnumber=15')]


def episodes(series_id, season_id):
    season = _get('/tv/catalog/series/%s/seasons/%s' % (series_id, season_id))
    embedded = season['_embedded']
    instalments = []
    if 'instalments' in embedded:
        instalments = embedded['instalments']
    else:
        instalments = embedded['episodes']
    return [program(item['prfId']) for item in instalments]


def seasons(series_id):
    return [Season.from_response(item) for item in
            _get('/tv/catalog/series/%s' % series_id,
                 '&embeddedInstalmentsPageSize=1')['_links']['seasons']]


def program(program_id):
    return Program.from_id(program_id)

def channels():
    chs = [Channel.from_response(item) for item in _get('/tv/live')]
    return [ch for ch in chs if ch.manifest]

def radios():
    rds = [Channel.from_response(item) for item in _get('/radio/live')]
    return [rd for rd in rds if rd.manifest]


def categories():
    items = _getDeep(_get('/tv/pages'), 'pageListItems')
    return [Category.from_response(item) for item in items]


def _to_series_or_program(item):
    if item.get('type', '') == 'series':
        return Series.from_response(item)
    return Program.from_response(item)


def programs(category_href):
    items = _get(category_href).get('pageListItems', [])
    items = [item for item in items if item.get('title', '').strip() != ''
             and item['hasOndemandRights']]
    return map(_to_series_or_program, items)


def _hit_to_series_or_program(item):
    hit_type = item.get('type', None)
    if hit_type == 'serie':
        return Series.from_response(item['hit'])
    elif hit_type == 'episode' or hit_type == 'program':
        return Program.from_response(item['hit'])
    return None


def search(query):
    response = _get('/search', '&q=' + query)
    if response['hits'] is None:
        return []
    return filter(None, map(_hit_to_series_or_program, response['hits']))
