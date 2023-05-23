from .pAPI import pAPI


def setup(bot):
    bot.add_cog(pAPI(bot))
