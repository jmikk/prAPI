import csv
import requests
from redbot.core import commands, data_manager
import random
import os
import discord

class cardMini(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
