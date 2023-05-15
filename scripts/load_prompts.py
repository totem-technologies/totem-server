import json

from totem.repos.models import Prompt

# load prompts from json file and save to db in the django model "Prompts"

with open("prompts.json") as f:
    data = json.load(f)

for prompt in data:
    plist = Prompt.objects.filter(prompt=prompt["prompt"])
    if len(plist) > 1:
        for i in range(1, len(plist)):
            plist[i].delete()
    p = Prompt.objects.get_or_create(prompt=prompt["prompt"], created_by_id=1)[0]
    p.tags.add(*prompt["tags"])
    p.save()
    print(p.pk, p.prompt)
