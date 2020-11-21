from datetime import datetime
from mattermostdriver import Driver
import pathlib
import json


def connect(host, username, login_token):
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

    return d, user_id_to_name, my_user_id


def select_team(d, my_user_id):
    teams = d.teams.get_user_teams(my_user_id)
    print("Found teams:")
    for i_team, team in enumerate(teams):
        print("{}\t{}\t{}".format(i_team, team["name"], team["id"]))
    team_idx = int(input("Select team by idx: "))
    team = teams[team_idx]
    print("Selected team", team["name"])
    return team


def select_channel(d, team, my_user_id, user_id_to_name):
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
    channel_input = input("Select channels by idx separated by comma: ")
    channel_idxs = channel_input.replace(" ", "").split(",")
    selected_channels = [channels[int(idx)] for idx in channel_idxs]
    print("Selected channel(s):", ", ".join([channel["display_name"] for channel in selected_channels]))
    return selected_channels


def export_channel(d, channel, user_id_to_name, output_base, before=None, after=None):
    # Sanitize channel name
    channel_name = channel["display_name"].replace("\\", "").replace("/", "")

    print("Exporting channel", channel_name)
    if after:
        after = datetime.strptime(after, '%Y-%m-%d').timestamp()
    if before:
        before = datetime.strptime(before, '%Y-%m-%d').timestamp()

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
    output_base = pathlib.Path(output_base) / channel_name
    if not output_base.exists():
        output_base.mkdir()
    # Simplify all posts to contain only username, date, message and files in chronological order
    simple_posts = []
    for i_post, post in enumerate(reversed(all_posts)):

        # Filter posts by date range
        created = post["create_at"] / 1000
        if (before and created > before) or (after and created < after):
            continue

        user_id = post["user_id"]
        if user_id not in user_id_to_name:
            user_id_to_name[user_id] = d.users.get_user(user_id)["username"]
        username = user_id_to_name[user_id]
        created = datetime.utcfromtimestamp(post["create_at"] / 1000).strftime('%Y-%m-%dT%H:%M:%SZ')
        message = post["message"]
        simple_post = dict(id=i_post, created=created, username=username, message=message)

        # If a code block is given in the message, dump it to file
        if message.count("```") > 1:
            start_pos = message.find("```") + 3
            end_pos = message.rfind("```")

            cut = message[start_pos:end_pos]
            if not len(cut):
                print("Code cut has no length")
            else:
                filename = "%03d" % i_post + "_code.txt"
                with open(output_base / filename, "w") as f:
                    f.write(cut)

        # If any files are attached to the message, download each
        if "files" in post["metadata"]:
            filenames = []
            for file in post["metadata"]["files"]:
                if download_files:
                    filename = "%03d" % i_post + "_" + file["name"]
                    print("Downloading", file["name"])
                    resp = d.files.get_file(file["id"])
                    # Mattermost Driver unfortunately parses json files to dicts
                    if isinstance(resp, dict):
                        with open(output_base / filename, "w") as f:
                            json.dump(resp, f)
                    else:
                        with open(output_base / filename, "wb") as f:
                            f.write(resp.content)

                filenames.append(file["name"])
            simple_post["files"] = filenames
        simple_posts.append(simple_post)

    # Export posts to json file
    output_filename = channel_name + ".json"
    with open(output_base / output_filename, "w", encoding='utf8') as f:
        json.dump(simple_posts, f, indent=2, ensure_ascii=False)
    print("Dumped channel texts to", output_filename)


if __name__ == '__main__':
    host = ""
    username = ""  # Your gitlab username
    login_token = ""  # Access Token. Can be extracted from Browser Inspector (MMAUTHTOKEN)
    output_base = "results/"
    download_files = True

    # Range of posts to be exported as string in format "YYYY-MM-DD". Use None if no filter should be applied
    after = None
    before = None

    d, user_id_to_name, my_user_id = connect(host, username, login_token)
    team = select_team(d, my_user_id)
    channels = select_channel(d, team, my_user_id, user_id_to_name)
    for channel in channels:
        export_channel(d, channel, user_id_to_name, output_base, before, after)
    print("Finished export")