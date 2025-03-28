from redbot.core import commands, Config
import discord
from discord import app_commands

class FantasyJobBoard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1357911)
        self.config.register_guild(jobs=[])

    def has_job_permission():
        async def predicate(ctx):
            role_id = 1113108765315715092
            return any(role.id == role_id for role in ctx.author.roles)
        return commands.check(predicate)

    @commands.group(name="jobboard", invoke_without_command=True)
    async def jobboard(self, ctx):
        """Base command for the job board."""
        await ctx.send_help(ctx.command)

    @jobboard.command(name="view")
    async def view_jobs(self, ctx):
        """View all available jobs."""
        jobs = await self.config.guild(ctx.guild).jobs()
        if not jobs:
            await ctx.send("🪶 The job board is currently empty.")
        else:
            embed = discord.Embed(title="📜 Fantasy Job Board", color=discord.Color.gold())
            for i, job in enumerate(jobs, 1):
                embed.add_field(name=f"Job {i}", value=job, inline=False)
            await ctx.send(embed=embed)

    @jobboard.command(name="add")
    @has_job_permission()
    async def add_job(self, ctx, *, job_description: str):
        """Add a job to the board (admins only)."""
        jobs = await self.config.guild(ctx.guild).jobs()
        jobs.append(job_description)
        await self.config.guild(ctx.guild).jobs.set(jobs)
        await ctx.send(f"✅ Job added: {job_description}")

    @jobboard.command(name="remove")
    @has_job_permission()
    async def remove_job(self, ctx, job_number: int):
        """Remove a job from the board by number (admins only)."""
        jobs = await self.config.guild(ctx.guild).jobs()
        if 0 < job_number <= len(jobs):
            removed = jobs.pop(job_number - 1)
            await self.config.guild(ctx.guild).jobs.set(jobs)
            await ctx.send(f"🗑️ Removed job: {removed}")
        else:
            await ctx.send("❌ Invalid job number.")

