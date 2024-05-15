from redbot.core import commands, Config
import asyncio
import datetime

def is_owner_overridable():
    def predicate(ctx):
        return False
    return commands.permissions_check(predicate)

class Merge(commands.Cog):
    """My custom cog"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_player = {
            "village_pop": 100,
            "food": 1000,
            "wood": 0,
            "stone": 0,
            "super_skills": [],
            "prestige": 0,
            "workers": {
                "wood": {"count": 0, "timestamp": None},
                "stone": {"count": 0, "timestamp": None},
                "food": {"count": 0, "timestamp": None}
            }
        }
        self.config.register_member(**default_player)

    def cog_unload(self):
        asyncio.create_task(self.client.aclose())

    @commands.group()
    async def merge(self, ctx):
        """Merge game commands"""
        pass

    @merge.command()
    async def assign(self, ctx, resource: str, num_workers: int):
        """Assign villagers to collect a resource (wood, stone, or food)."""
        user = ctx.author
        player_data = await self.config.member(user).all()

        if resource not in ["wood", "stone", "food"]:
            await ctx.send("Invalid resource. Please choose wood, stone, or food.")
            return

        if num_workers > player_data["village_pop"]:
            await ctx.send(f"You only have {player_data['village_pop']} villagers available.")
            return

        player_data["workers"][resource]["count"] += num_workers
        player_data["village_pop"] -= num_workers
        player_data["workers"][resource]["timestamp"] = datetime.datetime.now().timestamp()

        await self.config.member(user).set(player_data)
        await ctx.send(f"Assigned {num_workers} villagers to collect {resource}.")

    @merge.command()
    async def view_workers(self, ctx):
        """View the status of your workers."""
        user = ctx.author
        player_data = await self.config.member(user).all()
        workers = player_data["workers"]
        current_time = datetime.datetime.now().timestamp()

        def get_elapsed_time(worker):
            if worker["timestamp"]:
                return (current_time - worker["timestamp"]) / 3600
            return 0

        elapsed_wood = get_elapsed_time(workers["wood"])
        elapsed_stone = get_elapsed_time(workers["stone"])
        elapsed_food = get_elapsed_time(workers["food"])

        await ctx.send(
            f"Wood: {workers['wood']['count']} workers (Elapsed time: {elapsed_wood:.2f} hours)\n"
            f"Stone: {workers['stone']['count']} workers (Elapsed time: {elapsed_stone:.2f} hours)\n"
            f"Food: {workers['food']['count']} workers (Elapsed time: {elapsed_food:.2f} hours)"
        )

    @merge.command()
    async def collect(self, ctx, resource: str = None, num_workers: int = None):
        """Collect resources and unassign workers."""
        user = ctx.author
        player_data = await self.config.member(user).all()
        workers = player_data["workers"]
        current_time = datetime.datetime.now().timestamp()

        def get_resources_and_food(worker):
            if not worker["timestamp"]:
                return 0, 0
            elapsed_time = (current_time - worker["timestamp"]) / 3600
            food_consumed = int(elapsed_time) * worker["count"]
            resources_collected = worker["count"] * int(elapsed_time) * 2
            return resources_collected, food_consumed

        if resource is None:
            total_food_consumed = 0
            for res in ["wood", "stone", "food"]:
                resources_collected, food_consumed = get_resources_and_food(workers[res])
                player_data[res] += resources_collected
                total_food_consumed += food_consumed
                player_data["village_pop"] += workers[res]["count"]
                workers[res]["count"] = 0
                workers[res]["timestamp"] = None

            if player_data["food"] < total_food_consumed:
                await ctx.send("You have run out of food. Game over.")
                return

            player_data["food"] -= total_food_consumed
            await ctx.send(f"Collected all resources. Total food consumed: {total_food_consumed}")
        else:
            if resource not in ["wood", "stone", "food"]:
                await ctx.send("Invalid resource. Please choose wood, stone, or food.")
                return

            if workers[resource]["count"] == 0:
                await ctx.send(f"No workers assigned to collect {resource}.")
                return

            resources_collected, food_consumed = get_resources_and_food(workers[resource])

            if num_workers is not None:
                if num_workers > workers[resource]["count"]:
                    await ctx.send(f"You only have {workers[resource]['count']} workers assigned to {resource}.")
                    return

                resources_collected = (resources_collected / workers[resource]["count"]) * num_workers
                food_consumed = (food_consumed / workers[resource]["count"]) * num_workers
                workers[resource]["count"] -= num_workers
                player_data["village_pop"] += num_workers
            else:
                player_data["village_pop"] += workers[resource]["count"]
                workers[resource]["count"] = 0
                workers[resource]["timestamp"] = None

            if player_data["food"] < food_consumed:
                await ctx.send("You have run out of food. Game over.")
                return

            player_data["food"] -= food_consumed
            player_data[resource] += resources_collected
            await ctx.send(f"Collected {resources_collected} {resource}. Food consumed: {food_consumed}")

        await self.config.member(user).set(player_data)

    @merge.command()
    async def storage(self, ctx):
        """View your inventory."""
        user = ctx.author
        player_data = await self.config.member(user).all()

        await ctx.send(
            f"Village Population: {player_data['village_pop']}\n"
            f"Food: {player_data['food']}\n"
            f"Wood: {player_data['wood']}\n"
            f"Stone: {player_data['stone']}\n"
            f"Super Skills: {', '.join(player_data['super_skills']) if player_data['super_skills'] else 'None'}\n"
            f"Prestige: {player_data['prestige']}"
        )
