from datetime import datetime
from mattermostdriver import Driver
import pathlib
import json

host = "" # Mattermost url
username = "" # Your gitlab username
login_token = "" # Your Access Token. Can be extracted from Browser Inspector
output_base = "results/"
download_files = True

# Connect to server
d = Driver({
    "url": host,
    "port": 443,
    "token": login_token,
    "login_id": username

})
d.login()

# Get all usernames as we want to use those instead of the user ids
user_id_to_name = {}
page = 0
print("Downloading all user data")
while True:
    users_resp = d.users.get_users(params={"per_page": 200, "page": page})
    if len(users_resp) == 0:
        break
    for user in users_resp:
        user_id_to_name[user["id"]] = user["username"]
    page += 1

my_user_id = d.users.get_user_by_username(username)["id"]
print("Id of logged in user:", my_user_id)

teams = d.teams.get_user_teams(my_user_id)
print("Found teams:")
for i_team, team in enumerate(teams):
    print("{}\t{}\t{}".format(i_team, team["name"], team["id"]))

team_idx = int(input("Select team by idx: "))
team = teams[team_idx]
print("Selected team", team["name"])

channels = d.channels.get_channels_for_user(my_user_id, team["id"])

# Add display name to direct messages
for channel in channels:
    if channel["type"] != "D":
        continue

    # The channel name consists of two user ids connected by a double underscore
    user_ids = channel["name"].split("__")
    other_user_id = user_ids[1] if user_ids[0] == my_user_id else user_ids[0]
    channel["display_name"] = user_id_to_name[other_user_id]

# Sort channels by name for easier search
channels = sorted(channels, key=lambda x: x["display_name"].lower())

print("Found Channels:")
for i_channel, channel in enumerate(channels):
    print("{}\t{}\t{}".format(i_channel, channel["display_name"], channel["id"]))

channel_idx = int(input("Select channel by idx: "))
channel = channels[channel_idx]
print("Selected channel", channel["display_name"])

# Get all posts for selected channel
page = 0
all_posts = []
while True:
    print("Requesting channel page {}".format(page))
    posts = d.posts.get_posts_for_channel(channel["id"], params={"per_page": 200, "page": page})

    if len(posts["posts"]) == 0:
        # If no posts are returned, we have reached the end
        break

    all_posts.extend([posts["posts"][post] for post in posts["order"]])
    page += 1
print("Found {} posts".format(len(all_posts)))


# Create output directory
output_base = pathlib.Path(output_base)
if not output_base.exists():
    output_base.mkdir()

# Simplify all posts to contain only username, date, message and files in chronological order
simple_posts = []
for i_post, post in enumerate(reversed(all_posts)):
    user_id = post["user_id"]
    if user_id not in user_id_to_name:
        user_id_to_name[user_id] = d.users.get_user(user_id)["username"]
    username = user_id_to_name[user_id]
    created = datetime.utcfromtimestamp(post["create_at"]/1000).strftime('%Y-%m-%dT%H:%M:%SZ')
    simple_post = dict(id=i_post, created=created, username=username,  message=post["message"])

    # If any files are attached to the message, download each
    if "files" in post["metadata"]:
        filenames = []
        for file in post["metadata"]["files"]:
            if download_files:
                filename = "%03d" % i_post+"_"+file["name"]
                print("Downloading", file["name"])
                resp = d.files.get_file(file["id"])

                # Mattermost Driver unfortunately parses json files to dicts
                if isinstance(resp, dict):
                    content = json.dumps(resp)
                else:
                    content = resp.content

                with open(output_base / filename, "wb") as f:
                    f.write(content)
            filenames.append(file["name"])
        simple_post["files"] = filenames
    simple_posts.append(simple_post)

# Export posts to json file
output_filename = channel["display_name"]+".json"
with open(output_base / output_filename, "w", encoding='utf8') as f:
    json.dump(simple_posts, f, indent=2, ensure_ascii=False)
