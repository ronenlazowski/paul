import os
import sys
import asyncio
import datetime
import psutil
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord.ui import View, button

load_dotenv()
try:
    admins = list(map(int, os.getenv("ADMINS", "").split(",")))
except ValueError:
    admins = []
    print("Invalid ADMINS environment variable. Ensure it contains valid IDs.")

def developer_only():
    async def predicate(ctx):
        if ctx.author.id in admins:
            return True
        else:
            return False

    return commands.check(predicate)


class Restricted(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="devhelp")
    @developer_only()
    async def devhelp(self, ctx):
        view = DeveloperDashboardView(self.bot)
        await ctx.author.send(
            "Click a button to execute a developer command:", view=view
        )


class DeveloperDashboardView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Help", style=discord.ButtonStyle.blurple)
    async def helpdev_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await self.help(interaction)

    @discord.ui.button(label="Server List", style=discord.ButtonStyle.green)
    async def servers_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await self.servers(interaction)

    @discord.ui.button(label="Leave Server", style=discord.ButtonStyle.green)
    async def leave_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await self.leave(interaction)

    @discord.ui.button(label="Server Info", style=discord.ButtonStyle.green)
    async def serverinfo_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await self.serverinfo(interaction)

    @discord.ui.button(label="Bot Statistics", style=discord.ButtonStyle.green)
    async def botstats_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await self.botstats(interaction)

    @discord.ui.button(label="Broadcast Message", style=discord.ButtonStyle.red)
    async def broadcast_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await self.broadcast(interaction)

    @discord.ui.button(label="Restart Bot", style=discord.ButtonStyle.red)
    async def restart_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await self.restart(interaction)

    @discord.ui.button(label="Test Broadcast", style=discord.ButtonStyle.gray)
    async def test_broadcast_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await self.test_broadcast(interaction)

    async def servers(self, interaction: discord.Interaction):
        servers = [f"- {guild.name} - ({guild.id})" for guild in self.bot.guilds]
        try:
            with open("servers.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(servers))
            file = discord.File("servers.txt")
            await interaction.response.send_message(
                f"I am in `{len(self.bot.guilds)}` different servers.",
                file=file,
                ephemeral=True,
            )
        except (OSError, discord.DiscordException) as e:
            print(f"Error creating server list: {e}")
            await interaction.response.send_message(
                f"Error creating server list: {str(e)}", ephemeral=True
            )
        finally:
            if os.path.exists("servers.txt"):
                try:
                    os.remove("servers.txt")
                except (OSError, PermissionError) as e:
                    print(f"Error removing servers.txt: {e}")

    async def leave(self, interaction: discord.Interaction):
        class LeaveServerView(View):
            def __init__(self):
                super().__init__(timeout=60)
                self.cancelled = False

            @button(label="Cancel", style=discord.ButtonStyle.gray)
            async def cancel_button(self, interaction: discord.Interaction):
                self.cancelled = True
                self.stop()
                await interaction.response.send_message(
                    "Operation cancelled.", ephemeral=True
                )

        view = LeaveServerView()
        await interaction.response.send_message(
            "Please provide the server ID you'd like to leave. Or click Cancel to abort.",
            view=view,
            ephemeral=True,
        )

        original_channel = interaction.channel

        def check_message(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == original_channel.id
            )

        response_message = None
        try:
            task1 = asyncio.create_task(
                self.bot.wait_for("message", check=check_message, timeout=30.0)
            )
            task2 = asyncio.create_task(view.wait())

            done, pending = await asyncio.wait(
                [task1, task2], return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()

            finished_task = done.pop()

            if not view.cancelled:
                if finished_task == task1:
                    response_message = finished_task.result()
                else:
                    return
            else:
                return

        except asyncio.TimeoutError:
            await interaction.channel.send("Operation timed out. Please try again.")
            return
        except (discord.DiscordException, ValueError) as e:
            await interaction.channel.send(f"An error occurred: {str(e)}")
            return

        if response_message is None:
            return

        try:
            guild_id = int(response_message.content.strip())
            guild = self.bot.get_guild(guild_id)

            if guild is None:
                await interaction.channel.send(
                    f"The bot is not in a server with ID `{guild_id}`."
                )
                return

            class ConfirmLeaveView(View):
                def __init__(self):
                    super().__init__(timeout=30)
                    self.confirmed = False

                @button(label="Confirm Leave", style=discord.ButtonStyle.red)
                async def confirm_button(self, interaction: discord.Interaction):
                    self.confirmed = True
                    self.stop()
                    await interaction.response.send_message(
                        "Confirming server leave...", ephemeral=True
                    )

                @button(label="Cancel", style=discord.ButtonStyle.gray)
                async def cancel_confirm_button(self, interaction: discord.Interaction):
                    self.stop()
                    await interaction.response.send_message(
                        "Leave operation cancelled.", ephemeral=True
                    )

            confirm_view = ConfirmLeaveView()
            guild_name = guild.name
            await interaction.followup.send(
                f"Are you sure you want to leave **{guild_name}** (`{guild_id}`)? This action cannot be undone.",
                view=confirm_view,
            )

            await confirm_view.wait()

            if confirm_view.confirmed:
                await interaction.channel.send(
                    f"Leaving server **{guild_name}** (`{guild_id}`)..."
                )
                await guild.leave()
                await interaction.channel.send(f"Successfully left **{guild_name}**.")

        except ValueError:
            await interaction.channel.send(
                "Invalid server ID. Please provide a valid numeric ID."
            )

    async def serverinfo(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Please provide the server ID for which you'd like information.",
            ephemeral=True,
        )

        original_channel = interaction.channel

        def check_message(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == original_channel.id
            )

        try:
            response_message = await self.bot.wait_for(
                "message", check=check_message, timeout=30.0
            )

            guild_id = int(response_message.content.strip())
            guild = self.bot.get_guild(guild_id)

            if guild is None:
                await interaction.channel.send(
                    f"The bot is not in a server with ID `{guild_id}`."
                )
                return

            embed = discord.Embed(
                title=f"Server Information - {guild.name}", color=discord.Color.blue()
            )
            embed.add_field(name="Server ID", value=guild.id, inline=False)
            embed.add_field(name="Member Count", value=guild.member_count, inline=False)
            embed.add_field(
                name="Created At",
                value=guild.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                inline=False,
            )
            embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
            await interaction.channel.send(embed=embed)

        except ValueError:
            await interaction.channel.send(
                "Invalid server ID. Please provide a valid numeric ID."
            )
        except asyncio.TimeoutError:
            await interaction.channel.send("Operation timed out. Please try again.")
        except discord.DiscordException as e:
            await interaction.channel.send(f"An error occurred: {str(e)}")

    async def restart(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔄 Restarting bot...", ephemeral=True)
        python = sys.executable
        os.execl(python, python, *sys.argv)

    async def help(self, interaction: discord.Interaction):
        msg = discord.Embed(title="Developer Commands", color=discord.Colour.blue())
        msg.add_field(
            name="",
            value=(
                "**Server List -** Shows you the servers the bot is in.\n"
                "**Leave Server -** Leaves a server.\n"
                "**Server Info -** Gives information and statistics about a server.\n"
                "**Restart Bot -** Restarts the bot.\n"
                "**Broadcast Message -** Broadcasts a message to all servers.\n"
                "**Bot Statistics -** Displays bot statistics.\n"
            ),
            inline=False,
        )
        msg.set_footer(
            text="⚠️ - Some of these actions are global and will affect other servers!"
        )
        await interaction.response.send_message(embed=msg, ephemeral=True)

    async def broadcast(self, interaction: discord.Interaction):
        class BroadcastCancelView(View):
            def __init__(self):
                super().__init__(timeout=60)
                self.cancelled = False

            @button(label="Cancel", style=discord.ButtonStyle.gray)
            async def cancel_button(
                self, interaction: discord.Interaction, _: discord.ui.Button
            ):
                self.cancelled = True
                self.stop()
                await interaction.response.send_message(
                    "Broadcast operation cancelled.", ephemeral=True
                )

        view = BroadcastCancelView()
        await interaction.response.send_message(
            "Please provide the message to broadcast to all servers. Or click Cancel to abort.",
            view=view,
            ephemeral=True,
        )

        original_channel = interaction.channel

        def check_message(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == original_channel.id
            )

        try:
            task1 = asyncio.create_task(
                self.bot.wait_for("message", check=check_message, timeout=60.0)
            )
            task2 = asyncio.create_task(view.wait())

            done, pending = await asyncio.wait(
                [task1, task2], return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()

            if view.cancelled:
                return

            response_message = done.pop().result()
            message = response_message.content

            for guild in self.bot.guilds:
                main_channel = guild.system_channel or next(
                    (
                        channel
                        for channel in guild.text_channels
                        if channel.permissions_for(guild.me).send_messages
                    ),
                    None,
                )
                if main_channel:
                    try:
                        await main_channel.send(message)
                    except discord.Forbidden:
                        continue

            await interaction.followup.send(
                "Broadcast message sent to all servers.", ephemeral=True
            )

        except asyncio.TimeoutError:
            await interaction.followup.send(
                "Operation timed out. Please try again.", ephemeral=True
            )

    async def botstats(self, interaction: discord.Interaction):
        process = psutil.Process(os.getpid())
        memory_usage = process.memory_info().rss / 1024**2
        uptime = datetime.datetime.now(datetime.timezone.utc) - self.bot.start_time

        embed = discord.Embed(title="Bot Statistics", color=discord.Color.blue())
        embed.add_field(
            name="Uptime", value=str(uptime).split(".", maxsplit=1)[0], inline=False
        )
        embed.add_field(
            name="Memory Usage", value=f"{memory_usage:.2f} MB", inline=False
        )
        embed.add_field(name="Servers", value=f"{len(self.bot.guilds)}", inline=False)
        embed.add_field(
            name="Users",
            value=f"{sum(g.member_count for g in self.bot.guilds)}",
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def test_broadcast(self, interaction: discord.Interaction):
        class TestBroadcastView(View):
            def __init__(self):
                super().__init__(timeout=60)
                self.cancelled = False
                self.test_message = None

            @button(label="Cancel", style=discord.ButtonStyle.gray)
            async def cancel_button(
                self, interaction: discord.Interaction, _: discord.ui.Button
            ):
                self.cancelled = True
                self.stop()
                await interaction.response.send_message(
                    "Test broadcast operation cancelled.", ephemeral=True
                )

        view = TestBroadcastView()
        await interaction.response.send_message(
            "Please provide the message to test broadcast in this channel. Or click Cancel to abort.",
            view=view,
            ephemeral=True,
        )

        original_channel = interaction.channel

        def check_message(m):
            return (
                m.author.id == interaction.user.id
                and m.channel.id == original_channel.id
            )

        try:
            task1 = asyncio.create_task(
                self.bot.wait_for("message", check=check_message, timeout=60.0)
            )
            task2 = asyncio.create_task(view.wait())

            done, pending = await asyncio.wait(
                [task1, task2], return_when=asyncio.FIRST_COMPLETED
            )

            for task in pending:
                task.cancel()

            if view.cancelled:
                return

            response_message = done.pop().result()
            message = response_message.content

            await interaction.followup.send(message)

        except asyncio.TimeoutError:
            await interaction.followup.send(
                "Operation timed out. Please try again.", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Restricted(bot))
