quest_cog = self.bot.get_cog("FantasyJobBoard")
if quest_cog:
  await quest_cog.record_progress(
  member=ctx.author,
  game="Fill_in",
  objective="NAME",
  amount=1,
  debug=True
)
