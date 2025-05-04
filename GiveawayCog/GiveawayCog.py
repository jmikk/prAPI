class GiveawayButtonView(discord.ui.View):
    def __init__(self, role_id, card_data, card_link, role, end_time, message_id=None, saved_entrants=None):
        super().__init__(timeout=None)
        self.entrants = set()
        self.role_id = role_id
        self.card_data = card_data
        self.card_link = card_link
        self.role = role
        self.end_time = end_time
        self.message = None
        self.message_id = message_id

        if saved_entrants:
            self.entrants = set(saved_entrants)

    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.green, custom_id="giveaway:enter")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.role_id and self.role_id not in [role.id for role in interaction.user.roles]:
            await interaction.response.send_message("You don't have the required role to enter.", ephemeral=True)
            return

        self.entrants.add(interaction.user.id)

        # Save the entrant to config for persistence
        active = await self.view_config().active_giveaways()
        for entry in active:
            if entry["message_id"] == self.message_id:
                if interaction.user.id not in entry["entrants"]:
                    entry["entrants"].append(interaction.user.id)
                    await self.view_config().active_giveaways.set(active)
                break

        await interaction.response.send_message("You've entered the giveaway!", ephemeral=True)
        if self.message:
            await self.message.edit(embed=self.create_embed(), view=self)

    def get_entrants(self):
        return [self.message.guild.get_member(uid) for uid in self.entrants if self.message.guild.get_member(uid)]

    async def disable_all_items(self):
        for item in self.children:
            item.disabled = True
        self.stop()

    def create_embed(self):
        embed = discord.Embed(
            title=f"Giveaway: {self.card_data['name']} ({self.card_data['category'].title()} Season:{self.card_data['season']})",
            description=f"A {self.card_data['category'].title()} card is up for grabs!",
            url=self.card_link,
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=f"https://www.nationstates.net/images/flags/{self.card_data['flag']}")
        eligible_role = self.role.mention if self.role else "Everyone"
        embed.add_field(name="Market Value", value=f"{self.card_data['market_value']}", inline=True)
        embed.add_field(name="Eligible Role", value=eligible_role, inline=True)
        embed.add_field(name="Ends", value=f"<t:{int(self.end_time.timestamp())}:R>", inline=False)
        embed.add_field(name="Entrants", value=str(len(self.entrants)), inline=False)
        embed.set_footer(text="Click the button to enter!")
        return embed

    def view_config(self):
        return Config.get_conf(None, identifier=9006)  # Same identifier as the cog
