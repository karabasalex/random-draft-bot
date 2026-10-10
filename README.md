# Random Draft Bot

I made this for my friend group's **Deadlock** custom matches. Even after the
City Never Sleeps update, the in-game random hero option still behaves weirdly,
so figured I'd publish it.

Hop into a voice channel, type `/draft`, and it rolls up two random teams and
gives every player a unique random character.

## What it does

- Reads everyone in your voice channel and rolls two random teams.
- Extra people past the limit go on a **bench**.
- Hands out a **unique random character** to each player (no repeats).
- Every step has a reroll button, so you can keep rolling until it looks fair.

## Default modes

Both are Deadlock.
- **Standard (6v6)** — 12 players max.
- **Street Brawl (4v4)** — 8 players max.

## The `@Draftee` filter

Make a role called `Draftee` and give it to anyone who actually wants to play.

- If **anyone** in the channel has the role, only Draftees get drafted.
- If **nobody** has it, the bot assumes everyone in the channel is playing.

## Setup

1. **Make a Discord app.** In the
   [Discord Developer Portal](https://discord.com/developers/applications), create
   a new application. On the **Bot** tab, copy the token and turn on
   **Server Members Intent** under *Privileged Gateway Intents*. Then invite it
   with the `bot` and `applications.commands` scopes *(General → Permissions:
   **Send Messages** and **Embed Links**)*.

2. **Install the Python deps.**

   ```bash
   pip install -r requirements.txt
   ```

3. **Add your token.** Copy `.env.example` to `.env` and paste your token in:

   ```
   DISCORD_TOKEN=your_actual_token_here
   ```

4. **Run it.**

   ```bash
   python bot.py
   ```

## Adding your own game

1. Drop a character list in `character_pools/`, e.g.:

   ```json
   ["Character One", "Character Two", "Character Three"]
   ```

2. Add a mode block to `modes.json`:

   ```json
   "mygame_standard": {
     "display_name": "My Game (5v5)",
     "team_size": 5,
     "team_names": ["Red", "Blue"],
     "team_emojis": ["🔴", "🔵"],
     "character_pool_file": "character_pools/mygame.json",
     "filter_role": "Draftee",
     "theme_color": 15051068
   }
   ```

3. Restart the bot. It shows up in `/draft` automatically.
