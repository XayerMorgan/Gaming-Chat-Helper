Hyperline AI — image assets
==========================

Drop your own art here. The app reloads these on next launch.

Required / used automatically
-----------------------------
logo.png              Main brand mark (also used for window icon if app.ico missing)
logo_sm.png           Optional small header logo (falls back to logo.png)
app.ico               Windows taskbar / window icon
hyperline_icon.png    Transparent master art used to build app.ico
banner.png            Optional wide art under the header on Quick tab
                      (hide by deleting this file or set show_banner false in config)

Shared intent icons (all games — Library/UX consistency)
--------------------------------------------------------
Place PNGs in icons/ (128×128 transparent preferred):

  intent_lfg.png        Party / swords
  intent_activity.png   Compass / map
  intent_reply.png      Chat bubble / quill
  intent_recruit.png    Guild banner
  intent_noise.png      Chaos spark / dice

These icons are SHARED across every game profile so the Chat Generator
job row always feels the same. Per-game color chrome changes; icons stay.

Per-game badges
---------------
Place PNGs in games/ using these exact names:

  the_quinfall.png
  world_of_warcraft.png
  albion_online.png
  guild_wars_2.png
  custom_short.png

Per-game color themes live in code (GAME_THEMES). Switching games
recolors accents (gold for WoW, arcane violet for Quinfall, etc.)
but Library multi-select and tools stay the same.

Tips
----
• Prefer PNG with transparent background for logos/badges
• Logo looks best square (256×256 or larger)
• Banner looks best wide (~960×180 or 16:9)
• Game badges look best square (128×128)
• Intent icons look best square (128×128)
• Your files override the defaults when you replace them
