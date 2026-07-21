import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
from html import unescape
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from . import Event
from .source_registry import GENERIC_SOURCES, SourceConfig


HEADERS = {
    "User-Agent":