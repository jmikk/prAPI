from .prAPI import prAPI


def setup(bot):
    bot.add_cog(pAPI(bot))
