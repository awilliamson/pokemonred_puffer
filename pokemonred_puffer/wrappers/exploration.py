from collections import OrderedDict
import random
import gymnasium as gym
import numpy as np

from omegaconf import DictConfig
from pokemonred_puffer.environment import RedGymEnv
from pokemonred_puffer.global_map import local_to_global


class LRUCache:
    # initialising capacity
    def __init__(self, capacity: int):
        self.cache = OrderedDict()
        self.capacity = capacity

    def contains(self, key: tuple[int, int, int]) -> bool:
        if key not in self.cache:
            return False
        else:
            self.cache.move_to_end(key)
            return True

    def put(self, key: tuple[int, int, int]) -> tuple[int, int, int] | None:
        self.cache[key] = 1
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            return self.cache.popitem(last=False)[0]

    def clear(self):
        self.cache.clear()


# Yes. This wrapper mutates the env.
# Is that good? No.
# Am I doing it anyway? Yes.
# Why? To save memory
class DecayWrapper(gym.Wrapper):
    def __init__(self, env: RedGymEnv, reward_config: DictConfig):
        super().__init__(env)
        self.step_forgetting_factor = reward_config.step_forgetting_factor
        self.forgetting_frequency = reward_config.forgetting_frequency

    def step(self, action):
        if self.env.unwrapped.step_count % self.forgetting_frequency == 0:
            self.step_forget_explore()

        return self.env.step(action)

    def step_forget_explore(self):
        self.env.unwrapped.seen_coords.update(
            (k, max(0.15, v * (self.step_forgetting_factor["coords"])))
            for k, v in self.env.unwrapped.seen_coords.items()
        )
        self.env.unwrapped.seen_map_ids *= self.step_forgetting_factor["map_ids"]
        self.env.unwrapped.seen_npcs.update(
            (k, max(0.15, v * (self.step_forgetting_factor["npc"])))
            for k, v in self.env.unwrapped.seen_npcs.items()
        )
        self.env.unwrapped.seen_warps.update(
            (k, max(0.15, v * (self.step_forgetting_factor["coords"])))
            for k, v in self.env.unwrapped.seen_warps.items()
        )
        self.env.unwrapped.explore_map *= self.step_forgetting_factor["explore"]
        self.env.unwrapped.explore_map[self.env.unwrapped.explore_map > 0] = np.clip(
            self.env.unwrapped.explore_map[self.env.unwrapped.explore_map > 0], 0.15, 1
        )
        self.env.unwrapped.reward_explore_map *= self.step_forgetting_factor["explore"]
        self.env.unwrapped.reward_explore_map[self.env.unwrapped.explore_map > 0] = np.clip(
            self.env.unwrapped.reward_explore_map[self.env.unwrapped.explore_map > 0], 0.15, 1
        )
        self.env.unwrapped.seen_hidden_objs.update(
            (k, max(0.15, v * (self.step_forgetting_factor["hidden_objs"])))
            for k, v in self.env.unwrapped.seen_coords.items()
        )
        self.env.unwrapped.seen_signs.update(
            (k, max(0.15, v * (self.step_forgetting_factor["signs"])))
            for k, v in self.env.unwrapped.seen_signs.items()
        )
        self.env.unwrapped.safari_zone_steps.update(
            (k, max(0.15, v * (self.step_forgetting_factor["safari_zone_steps"])))
            for k, v in self.env.unwrapped.safari_zone_steps.items()
        )

        if self.env.unwrapped.read_m("wIsInBattle") == 0:
            self.env.unwrapped.seen_start_menu *= self.step_forgetting_factor["start_menu"]
            self.env.unwrapped.seen_pokemon_menu *= self.step_forgetting_factor["pokemon_menu"]
            self.env.unwrapped.seen_stats_menu *= self.step_forgetting_factor["stats_menu"]
            self.env.unwrapped.seen_bag_menu *= self.step_forgetting_factor["bag_menu"]
            self.env.unwrapped.seen_action_bag_menu *= self.step_forgetting_factor[
                "action_bag_menu"
            ]


class MaxLengthWrapper(gym.Wrapper):
    def __init__(self, env: RedGymEnv, reward_config: DictConfig):
        super().__init__(env)
        self.capacity = reward_config.capacity
        self.cache = LRUCache(capacity=self.capacity)

    def step(self, action):
        if self.env.unwrapped.step_count >= self.env.unwrapped.get_max_steps():
            self.cache.clear()

        step = self.env.step(action)
        player_x, player_y, map_n = self.env.unwrapped.get_game_coords()
        # Walrus operator does not support tuple unpacking
        if coord := self.cache.put((player_x, player_y, map_n)):
            x, y, n = coord
            del self.env.unwrapped.seen_coords[(x, y, n)]
            self.env.unwrapped.explore_map[local_to_global(y, x, n)] = 0
            self.env.unwrapped.reward_explore_map[local_to_global(y, x, n)] = 0
        return step


class OnResetExplorationWrapper(gym.Wrapper):
    def __init__(self, env: RedGymEnv, reward_config: DictConfig):
        super().__init__(env)
        self.full_reset_frequency = reward_config.full_reset_frequency
        self.jitter = reward_config.jitter
        self.counter = 0

    def step(self, action):
        if self.env.unwrapped.step_count >= self.env.unwrapped.get_max_steps():
            if (self.counter + random.randint(0, self.jitter)) >= self.full_reset_frequency:
                self.counter = 0
                self.env.unwrapped.explore_map *= 0
                self.env.unwrapped.reward_explore_map *= 0
                self.env.unwrapped.cut_explore_map *= 0
                self.env.unwrapped.cut_tiles.clear()
                self.env.unwrapped.seen_coords.clear()
                self.env.unwrapped.seen_map_ids *= 0
                self.env.unwrapped.seen_npcs.clear()
                self.env.unwrapped.valid_cut_coords.clear()
                self.env.unwrapped.invalid_cut_coords.clear()
                self.env.unwrapped.valid_pokeflute_coords.clear()
                self.env.unwrapped.invalid_pokeflute_coords.clear()
                self.env.unwrapped.pokeflute_tiles.clear()
                self.env.unwrapped.valid_surf_coords.clear()
                self.env.unwrapped.invalid_surf_coords.clear()
                self.env.unwrapped.surf_tiles.clear()
                self.env.unwrapped.seen_warps.clear()
                self.env.unwrapped.seen_hidden_objs.clear()
                self.env.unwrapped.seen_signs.clear()
                self.env.unwrapped.safari_zone_steps.update(
                    (k, 0) for k in self.env.unwrapped.safari_zone_steps.keys()
                )
            self.counter += 1
        return self.env.step(action)


class OnResetLowerToFixedValueWrapper(gym.Wrapper):
    def __init__(self, env: RedGymEnv, reward_config: DictConfig):
        super().__init__(env)
        self.fixed_value = reward_config.fixed_value

    def step(self, action):
        if self.env.unwrapped.step_count >= self.env.unwrapped.get_max_steps():
            self.env.unwrapped.seen_coords.update(
                (k, self.fixed_value["coords"])
                for k, v in self.env.unwrapped.seen_coords.items()
                if v > 0
            )
            self.env.unwrapped.seen_map_ids[self.env.unwrapped.seen_map_ids > 0] = self.fixed_value[
                "map_ids"
            ]
            self.env.unwrapped.seen_npcs.update(
                (k, self.fixed_value["npc"])
                for k, v in self.env.unwrapped.seen_npcs.items()
                if v > 0
            )
            self.env.unwrapped.valid_cut_coords.update(
                (k, self.fixed_value["valid_cut"])
                for k, v in self.env.unwrapped.seen_npcs.items()
                if v > 0
            )
            self.env.unwrapped.invalid_cut_coords.update(
                (k, self.fixed_value["invalid_cut"])
                for k, v in self.env.unwrapped.seen_npcs.items()
                if v > 0
            )
            self.env.unwrapped.valid_pokeflute_coords.update(
                (k, self.fixed_value["valid_pokeflute"])
                for k, v in self.env.unwrapped.seen_npcs.items()
                if v > 0
            )
            self.env.unwrapped.invalid_pokeflute_coords.update(
                (k, self.fixed_value["invalid_pokeflute"])
                for k, v in self.env.unwrapped.seen_npcs.items()
                if v > 0
            )
            self.env.unwrapped.valid_surf_coords.update(
                (k, self.fixed_value["valid_surf"])
                for k, v in self.env.unwrapped.seen_npcs.items()
                if v > 0
            )
            self.env.unwrapped.invalid_surf_coords.update(
                (k, self.fixed_value["invalid_surf"])
                for k, v in self.env.unwrapped.seen_npcs.items()
                if v > 0
            )
            self.env.unwrapped.explore_map[self.env.unwrapped.explore_map > 0] = self.fixed_value[
                "explore"
            ]
            self.env.unwrapped.reward_explore_map[self.env.unwrapped.reward_explore_map > 0] = (
                self.fixed_value["explore"]
            )
            self.env.unwrapped.cut_explore_map[self.env.unwrapped.cut_explore_map > 0] = (
                self.fixed_value["invalid_cut"]
            )
            self.env.unwrapped.seen_warps.update(
                (k, self.fixed_value["coords"])
                for k, v in self.env.unwrapped.seen_warps.items()
                if v > 0
            )
            self.env.unwrapped.seen_hidden_objs.update(
                (k, self.fixed_value["hidden_objs"])
                for k, v in self.env.unwrapped.seen_npcs.items()
                if v > 0
            )
            self.env.unwrapped.seen_signs.update(
                (k, self.fixed_value["signs"])
                for k, v in self.env.unwrapped.seen_npcs.items()
                if v > 0
            )
            self.env.unwrapped.safari_zone_steps.update(
                (k, self.fixed_value["safari_zone_steps"])
                for k, v in self.env.unwrapped.safari_zone_steps.items()
                if v > 0
            )
        return self.env.unwrapped.step(action)
