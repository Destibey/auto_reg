import unittest
from datetime import datetime

from platforms.chatgpt.constants import (
    MAX_REGISTRATION_AGE,
    MIN_REGISTRATION_AGE,
    generate_random_user_info,
)
from platforms.chatgpt.utils import generate_random_birthday


class ChatGPTBirthdateRangeTests(unittest.TestCase):
    def test_generate_random_user_info_age_stays_within_20_to_45(self):
        for _ in range(50):
            user_info = generate_random_user_info()
            age = int(user_info["age"])
            self.assertGreaterEqual(age, MIN_REGISTRATION_AGE)
            self.assertLessEqual(age, MAX_REGISTRATION_AGE)
            self.assertNotIn("birthdate", user_info)

    def test_generate_random_birthday_stays_within_20_to_45(self):
        current_year = datetime.now().year

        for _ in range(50):
            birthdate = generate_random_birthday()
            birth_year = int(birthdate.split("-", 1)[0])
            age = current_year - birth_year
            self.assertGreaterEqual(age, MIN_REGISTRATION_AGE)
            self.assertLessEqual(age, MAX_REGISTRATION_AGE)


if __name__ == "__main__":
    unittest.main()
