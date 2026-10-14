"""Eval: does the real interpreter tell food requests from off-topic ones (specs/002-off-topic-requests, SC-003)?

Calls the model named by AI_SEARCH_MODEL once per prompt, so it costs money, needs the
provider's API key, and its results vary a little between runs. That is why it lives here,
outside `manage.py test`. Run it whenever the interpreter instructions or the model change.
"""

from django.core.management.base import BaseCommand, CommandError

from queries.services.generation import LLMInterpreter

OFF_TOPIC = (
    "recommend a movie",
    "write me a poem about the sea",
    "what's the weather tomorrow",
    "fix my Python code",
    "who won the world cup",
    "translate hello into French",
    "tell me a joke",
    "how do I change a tyre",
    "book me a flight to Lisbon",
    "what is 17 times 23",
)
FOOD = (
    "I'm starving",
    "something light",
    "high protein breakfast",
    "comfort food",
    "low carb dinner",
    "what can I make with eggs",
    "quick lunch",
    "something warm and high in fibre",
    "vegan dessert",
    "healthy snack",
    "I'm sad, cook me something comforting",
    "how much fiber should I eat",
    "pasta",
    "meal prep for the week",
    "post-workout meal",
    "kid-friendly dinner",
    "something spicy",
    "a light salad",
    "gluten free bread",
    "soup",
)
# SC-003: at least 90% of off-topic prompts declined, at most 2% of food prompts wrongly declined.
MIN_DECLINED = 0.9
MAX_WRONGLY_DECLINED = 0.02


class Command(BaseCommand):
    help = "Run the off-topic eval against the real model and fail below SC-003's thresholds."

    def handle(self, *args, **options):
        interpreter = LLMInterpreter()
        declined = [p for p in OFF_TOPIC if not interpreter.interpret(p).on_topic]
        wrongly_declined = [p for p in FOOD if not interpreter.interpret(p).on_topic]

        declined_rate = len(declined) / len(OFF_TOPIC)
        wrong_rate = len(wrongly_declined) / len(FOOD)
        self.stdout.write(f"Off-topic declined: {len(declined)}/{len(OFF_TOPIC)} ({declined_rate:.0%})")
        for prompt in sorted(set(OFF_TOPIC) - set(declined)):
            self.stdout.write(f"  missed: {prompt!r}")
        self.stdout.write(f"Food wrongly declined: {len(wrongly_declined)}/{len(FOOD)} ({wrong_rate:.0%})")
        for prompt in wrongly_declined:
            self.stdout.write(f"  wrongly declined: {prompt!r}")

        if declined_rate < MIN_DECLINED or wrong_rate > MAX_WRONGLY_DECLINED:
            raise CommandError("Below SC-003 thresholds.")
        self.stdout.write(self.style.SUCCESS("Within SC-003 thresholds."))
