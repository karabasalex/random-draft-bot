"""Random Draft Bot. Run with: python bot.py"""

import json
import os
import random

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODES_FILE = os.path.join(BASE_DIR, "modes.json")


def load_modes():
    try:
        with open(MODES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print("Couldn't find modes.json!")
    except json.JSONDecodeError as e:
        print("modes.json has a typo:", e)
    return {}


def load_character_pool(path):
    full_path = os.path.join(BASE_DIR, path)
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        print(path, "should just be a list of names")
    except FileNotFoundError:
        print("Couldn't find the character pool at", full_path)
    except json.JSONDecodeError as e:
        print(path, "has a typo:", e)
    return []


def default_mode_key(modes):
    return next(iter(modes), None)


def member_has_role(member, role_name):
    # not case sensitive
    if not role_name:
        return False
    return any(r.name.lower() == role_name.lower() for r in member.roles)



# if someone in the call has the filter role then only those people will be drafted 
# if nobody has it we assume the whole call is playing
def pick_players(voice_channel, mode):
    humans = [m for m in voice_channel.members if not m.bot]
    role_name = mode.get("filter_role", "")
    draftees = [m for m in humans if member_has_role(m, role_name)]

    if draftees:
        spectators = [m for m in humans if m not in draftees]
        return draftees, spectators, True
    return humans, [], False


# if it's an odd number team1 just takes the extra one (so for example 4v3)
def shuffle_teams(players, mode):
    capacity = mode["team_size"] * 2
    pool = list(players)
    random.shuffle(pool)

    active = pool[:capacity]
    bench = pool[capacity:]

    half = (len(active) + 1) // 2
    return active[:half], active[half:], bench


def format_players(players):
    if not players:
        return "—"
    return "\n".join(p.display_name for p in players)


# only shown when there's actually someone on the bench or spectating
def bench_field_text(bench, spectators):
    lines = []
    if bench:
        lines.append("**Bench:**\n" + format_players(bench))
    if spectators:
        lines.append("**Spectators:**\n" + format_players(spectators))
    return "\n".join(lines)


intents = discord.Intents.default()
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)


async def mode_autocomplete(interaction, current):
    modes = load_modes()
    choices = []
    for key, data in modes.items():
        label = data.get("display_name", key)
        if current.lower() in label.lower() or current.lower() in key.lower():
            choices.append(app_commands.Choice(name=label, value=key))
    return choices[:25]


# phase 1, pick the teams
class DraftView(discord.ui.View):
    def __init__(self, mode, team1, team2, bench, spectators, filtered):
        super().__init__(timeout=600)
        self.mode = mode
        self.team1 = team1
        self.team2 = team2
        self.bench = bench
        self.spectators = spectators
        self.filtered = filtered

        # everyone who could still get drafted, so reroll can reshuffle all of them
        self.eligible = list(team1) + list(team2) + list(bench)

        self.lock_button.label = "⚔️ Lock Teams & Pick Characters"

    def build_embed(self):
        mode = self.mode
        embed = discord.Embed(
            title=f"⚖️ Team Draft — {mode['display_name']}",
            color=mode["theme_color"],
        )

        if self.filtered:
            embed.description = f"Only members with the **{mode['filter_role']}** role are drafting."
        else:
            embed.description = "Nobody had the filter role, so everyone in the voice channel is drafting."

        embed.add_field(
            name=f"{mode['team_emojis'][0]} {mode['team_names'][0]}",
            value=format_players(self.team1),
            inline=True,
        )
        embed.add_field(
            name=f"{mode['team_emojis'][1]} {mode['team_names'][1]}",
            value=format_players(self.team2),
            inline=True,
        )

        extra = bench_field_text(self.bench, self.spectators)
        if extra:
            embed.add_field(name="🛋️ Bench & Spectators", value=extra, inline=False)

        return embed

    @discord.ui.button(label="🎲 Reroll Teams", style=discord.ButtonStyle.primary, row=0)
    async def reroll_button(self, interaction, button):
        self.team1, self.team2, self.bench = shuffle_teams(self.eligible, self.mode)
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="⚔️ Lock Teams & Pick", style=discord.ButtonStyle.success, row=0)
    async def lock_button(self, interaction, button):
        pool = load_character_pool(self.mode["character_pool_file"])
        if len(pool) < len(self.team1) + len(self.team2):
            await interaction.response.send_message(
                "Not enough characters in the pool for this many players!", ephemeral=True
            )
            return

        view = CharacterDraftView(self.mode, self.team1, self.team2, self.bench, self.spectators, pool)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=0)
    async def cancel_button(self, interaction, button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Draft cancelled.", embed=None, view=self)


# phase 2, hand out the characters
class CharacterDraftView(discord.ui.View):
    def __init__(self, mode, team1, team2, bench, spectators, pool):
        super().__init__(timeout=600)
        self.mode = mode
        self.team1 = team1
        self.team2 = team2
        self.bench = bench
        self.spectators = spectators
        self.pool = pool
        self.picks1 = {}
        self.picks2 = {}

        self.reroll_button.label = "🎲 Reroll Characters"
        self.assign()

    # random.sample never hands out the same character twice
    def assign(self):
        chosen = random.sample(self.pool, len(self.team1) + len(self.team2))
        self.picks1 = dict(zip(self.team1, chosen[:len(self.team1)]))
        self.picks2 = dict(zip(self.team2, chosen[len(self.team1):]))

    def lines(self, picks):
        if not picks:
            return "—"
        return "\n".join(f"`{p.display_name}` ➔ {name}" for p, name in picks.items())

    def build_embed(self):
        mode = self.mode
        embed = discord.Embed(
            title=f"🎮 Characters Assigned — {mode['display_name']}",
            color=mode["theme_color"],
        )

        embed.add_field(
            name=f"{mode['team_emojis'][0]} {mode['team_names'][0]}",
            value=self.lines(self.picks1),
            inline=True,
        )
        embed.add_field(
            name=f"{mode['team_emojis'][1]} {mode['team_names'][1]}",
            value=self.lines(self.picks2),
            inline=True,
        )

        extra = bench_field_text(self.bench, self.spectators)
        if extra:
            embed.add_field(name="🛋️ Bench & Spectators", value=extra, inline=False)

        return embed

    @discord.ui.button(label="🎲 Reroll", style=discord.ButtonStyle.primary, row=0)
    async def reroll_button(self, interaction, button):
        self.assign()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="🏁 Done", style=discord.ButtonStyle.success, row=0)
    async def done_button(self, interaction, button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


@bot.tree.command(name="draft", description="Roll up random teams for a custom match.")
@app_commands.describe(mode="Which mode to draft for (defaults to the first one).")
@app_commands.autocomplete(mode=mode_autocomplete)
async def draft(interaction, mode: str = None):
    modes = load_modes()
    if not modes:
        await interaction.response.send_message("Couldn't read modes.json, nothing to draft!", ephemeral=True)
        return

    if mode is None:
        mode = default_mode_key(modes)
    if mode not in modes:
        await interaction.response.send_message("I don't know that mode.", ephemeral=True)
        return
    config = modes[mode]

    member = interaction.user
    voice_channel = member.voice.channel if isinstance(member, discord.Member) and member.voice else None
    if not voice_channel:
        await interaction.response.send_message("Hop into a voice channel first!", ephemeral=True)
        return

    eligible, spectators, filtered = pick_players(voice_channel, config)
    if len(eligible) < 2:
        await interaction.response.send_message("Need at least 2 people in the voice channel!", ephemeral=True)
        return

    team1, team2, bench = shuffle_teams(eligible, config)
    view = DraftView(config, team1, team2, bench, spectators, filtered)
    await interaction.response.send_message(embed=view.build_embed(), view=view)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync()
    print("Synced slash commands.")


bot.run(TOKEN)
