#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {

constexpr int kUniverse = 25;
constexpr int kCardSize = 15;
constexpr int kComplementSize = 10;
constexpr int kCards = 4;
constexpr int kPatterns = 16;
constexpr long long kOutcomeSpace = 3268760;
constexpr long long kSingleCoverage14 = 151;
constexpr long long kSingleCoverage13 = 4876;

struct Half {
    std::array<unsigned char, 8> counts{};
    std::array<unsigned char, 3> margins{};
};

struct Metrics {
    std::array<long long, 16> histogram{};
    long long best_hits_sum = 0;
    long long ge11 = 0;
    long long ge12 = 0;
    long long ge13 = 0;
    long long ge14 = 0;
    long long ge15 = 0;
};

std::vector<Half> first_half;
std::unordered_map<int, std::vector<std::array<unsigned char, 8>>> second_half;
std::array<int, kPatterns> membership{};

void generate_compositions(
    int total,
    int position,
    std::array<unsigned char, 8>& counts,
    bool bit0_is_one
) {
    if (position == 7) {
        counts[7] = static_cast<unsigned char>(total);
        std::array<int, 3> margins{};
        for (int index = 0; index < 8; ++index) {
            const int pattern = 2 * index + (bit0_is_one ? 1 : 0);
            for (int card = 1; card < kCards; ++card) {
                if (pattern & (1 << card)) {
                    margins[card - 1] += counts[index];
                }
            }
        }
        if (bit0_is_one) {
            Half half;
            half.counts = counts;
            for (int card = 0; card < 3; ++card) {
                half.margins[card] = static_cast<unsigned char>(margins[card]);
            }
            first_half.push_back(half);
        } else {
            const int key = margins[0] * 256 + margins[1] * 16 + margins[2];
            second_half[key].push_back(counts);
        }
        return;
    }
    for (int value = 0; value <= total; ++value) {
        counts[position] = static_cast<unsigned char>(value);
        generate_compositions(total - value, position + 1, counts, bit0_is_one);
    }
}

bool complement_witness_dfs(
    const std::vector<std::pair<int, int>>& groups,
    int index,
    int selected,
    std::array<int, kCards>& intersections,
    std::array<int, kCards>& remaining_capacity,
    int remaining_count,
    int required_intersection
) {
    if (selected == kComplementSize) {
        return intersections[0] >= required_intersection
            && intersections[1] >= required_intersection
            && intersections[2] >= required_intersection
            && intersections[3] >= required_intersection;
    }
    if (index == static_cast<int>(groups.size())
        || selected > kComplementSize
        || selected + remaining_count < kComplementSize) {
        return false;
    }
    for (int card = 0; card < kCards; ++card) {
        if (intersections[card]
                + std::min(kComplementSize - selected, remaining_capacity[card])
            < required_intersection) {
            return false;
        }
    }

    const int pattern = groups[index].first;
    const int count = groups[index].second;
    std::array<int, kCards> next_capacity = remaining_capacity;
    for (int card = 0; card < kCards; ++card) {
        if (pattern & (1 << card)) {
            next_capacity[card] -= count;
        }
    }

    const int max_take = std::min(count, kComplementSize - selected);
    const int min_take = std::max(
        0,
        kComplementSize - selected - (remaining_count - count)
    );
    for (int take = max_take; take >= min_take; --take) {
        std::array<int, kCards> next_intersections = intersections;
        for (int card = 0; card < kCards; ++card) {
            if (pattern & (1 << card)) {
                next_intersections[card] += take;
            }
        }
        if (complement_witness_dfs(
                groups,
                index + 1,
                selected + take,
                next_intersections,
                next_capacity,
                remaining_count - count,
                required_intersection)) {
            return true;
        }
    }
    return false;
}

bool has_complement_witness(int required_intersection) {
    std::vector<std::pair<int, int>> groups;
    std::array<int, kCards> capacities{};
    for (int pattern = 0; pattern < kPatterns; ++pattern) {
        if (membership[pattern] == 0) {
            continue;
        }
        groups.push_back({pattern, membership[pattern]});
        for (int card = 0; card < kCards; ++card) {
            if (pattern & (1 << card)) {
                capacities[card] += membership[pattern];
            }
        }
    }
    std::sort(
        groups.begin(),
        groups.end(),
        [](const auto& left, const auto& right) {
            return __builtin_popcount(static_cast<unsigned>(left.first))
                > __builtin_popcount(static_cast<unsigned>(right.first));
        }
    );
    std::array<int, kCards> intersections{};
    return complement_witness_dfs(
        groups,
        0,
        0,
        intersections,
        capacities,
        kUniverse,
        required_intersection
    );
}

int max_pair_overlap() {
    int maximum = 0;
    for (int left = 0; left < kCards; ++left) {
        for (int right = left + 1; right < kCards; ++right) {
            int overlap = 0;
            for (int pattern = 0; pattern < kPatterns; ++pattern) {
                if ((pattern & (1 << left)) && (pattern & (1 << right))) {
                    overlap += membership[pattern];
                }
            }
            maximum = std::max(maximum, overlap);
        }
    }
    return maximum;
}

long long choose_small(int n, int k) {
    if (k < 0 || k > n) {
        return 0;
    }
    k = std::min(k, n - k);
    long long value = 1;
    for (int step = 1; step <= k; ++step) {
        value = value * (n - step + 1) / step;
    }
    return value;
}

Metrics evaluate_exact() {
    using Key = std::uint32_t;
    std::vector<std::pair<Key, long long>> current;
    current.push_back({0, 1});

    for (int pattern = 0; pattern < kPatterns; ++pattern) {
        const int group_count = membership[pattern];
        if (group_count == 0) {
            continue;
        }
        std::unordered_map<Key, long long> accumulated;
        accumulated.reserve(current.size() * 3 + 16);
        for (const auto& state : current) {
            const Key key = state.first;
            const long long ways = state.second;
            const int selected = static_cast<int>(key & 31u);
            const int max_take = std::min(group_count, kCardSize - selected);
            for (int take = 0; take <= max_take; ++take) {
                Key next = (key & ~31u) | static_cast<Key>(selected + take);
                if (take) {
                    for (int card = 0; card < kCards; ++card) {
                        if (pattern & (1 << card)) {
                            next += static_cast<Key>(take) << (5 + 4 * card);
                        }
                    }
                }
                accumulated[next] += ways * choose_small(group_count, take);
            }
        }
        current.clear();
        current.reserve(accumulated.size());
        for (const auto& state : accumulated) {
            current.push_back(state);
        }
    }

    Metrics metrics;
    long long total = 0;
    for (const auto& state : current) {
        const std::uint32_t key = state.first;
        const long long ways = state.second;
        if (static_cast<int>(key & 31u) != kCardSize) {
            continue;
        }
        int best_hits = 0;
        for (int card = 0; card < kCards; ++card) {
            best_hits = std::max(
                best_hits,
                static_cast<int>((key >> (5 + 4 * card)) & 15u)
            );
        }
        metrics.histogram[best_hits] += ways;
        metrics.best_hits_sum += static_cast<long long>(best_hits) * ways;
        total += ways;
    }
    if (total != kOutcomeSpace) {
        std::cerr << "GLOBAL_NATIVE_OUTCOME_COUNT_MISMATCH observed=" << total
                  << " expected=" << kOutcomeSpace << "\n";
        std::exit(20);
    }
    for (int hits = 0; hits <= kCardSize; ++hits) {
        if (hits >= 11) metrics.ge11 += metrics.histogram[hits];
        if (hits >= 12) metrics.ge12 += metrics.histogram[hits];
        if (hits >= 13) metrics.ge13 += metrics.histogram[hits];
        if (hits >= 14) metrics.ge14 += metrics.histogram[hits];
        if (hits >= 15) metrics.ge15 += metrics.histogram[hits];
    }
    return metrics;
}

void print_array(const std::array<int, kPatterns>& values) {
    std::cout << "[";
    for (int index = 0; index < kPatterns; ++index) {
        if (index) std::cout << ",";
        std::cout << values[index];
    }
    std::cout << "]";
}

void print_histogram(const std::array<long long, 16>& values) {
    std::cout << "{";
    bool first = true;
    for (int hits = 0; hits <= kCardSize; ++hits) {
        if (!values[hits]) continue;
        if (!first) std::cout << ",";
        first = false;
        std::cout << "\"" << hits << "\":" << values[hits];
    }
    std::cout << "}";
}

}  // namespace

int main() {
    std::array<unsigned char, 8> composition{};
    generate_compositions(kCardSize, 0, composition, true);
    generate_compositions(kUniverse - kCardSize, 0, composition, false);

    const auto started = std::chrono::steady_clock::now();
    long long feasible_histograms = 0;
    long long floor_ge_9_histograms = 0;
    long long floor_ge_10_histograms = 0;
    long long coverage13_optimal_class_histograms = 0;

    std::tuple<long long, long long, long long> best_objective{-1, -1, -1};
    std::array<int, kPatterns> best_membership{};
    Metrics best_metrics;

    for (const Half& first : first_half) {
        const int key =
            (kCardSize - first.margins[0]) * 256
            + (kCardSize - first.margins[1]) * 16
            + (kCardSize - first.margins[2]);
        const auto found = second_half.find(key);
        if (found == second_half.end()) {
            continue;
        }
        for (const auto& second : found->second) {
            membership.fill(0);
            for (int index = 0; index < 8; ++index) {
                membership[2 * index + 1] = first.counts[index];
                membership[2 * index] = second[index];
            }
            ++feasible_histograms;

            // A 15-number draw Y has <= 8 hits in every card iff its 10-number
            // complement X intersects every card in at least 7 positions.
            // Absence of such X proves portfolio floor >= 9.
            const bool floor_at_least_9 = !has_complement_witness(7);
            if (floor_at_least_9) {
                ++floor_ge_9_histograms;
            }

            // Similarly, absence of an X intersecting every card in >= 6 would
            // imply floor >= 10. Exhaustion proves this never occurs.
            const bool floor_at_least_10 = !has_complement_witness(6);
            if (floor_at_least_10) {
                ++floor_ge_10_histograms;
            }

            if (!floor_at_least_9) {
                continue;
            }

            // After floor=9 and four distinct cards maximize Q15=4, Q14 has
            // global union upper bound 4*151 and Q13 has 4*4876. Q13 reaches
            // that bound iff radius-2 Johnson balls are pairwise disjoint,
            // equivalent here to pairwise card overlap <= 10.
            if (max_pair_overlap() > 10) {
                continue;
            }
            ++coverage13_optimal_class_histograms;
            const Metrics metrics = evaluate_exact();
            const auto objective = std::make_tuple(
                metrics.ge12,
                metrics.ge11,
                metrics.best_hits_sum
            );
            if (objective > best_objective) {
                best_objective = objective;
                best_membership = membership;
                best_metrics = metrics;
            }
        }
    }

    const double elapsed = std::chrono::duration<double>(
        std::chrono::steady_clock::now() - started
    ).count();

    if (feasible_histograms != 1977452
        || floor_ge_9_histograms != 54520
        || floor_ge_10_histograms != 0
        || coverage13_optimal_class_histograms != 14856
        || best_metrics.ge15 != 4
        || best_metrics.ge14 != 604
        || best_metrics.ge13 != 19504
        || best_metrics.ge12 != 237504
        || best_metrics.ge11 != 1310584
        || best_metrics.best_hits_sum != 33982067) {
        std::cerr << "GLOBAL_NATIVE_CERTIFICATE_REGRESSION\n";
        return 30;
    }

    std::cout << "{";
    std::cout << "\"schema_version\":1,";
    std::cout << "\"status\":\"GLOBAL_ORBIT_SEARCH_PROVEN\",";
    std::cout << "\"method\":\"EXHAUSTIVE_MEMBERSHIP_HISTOGRAM_CERTIFICATE_4_CARD_V1\",";
    std::cout << "\"card_count\":4,";
    std::cout << "\"full_card_space\":3268760,";
    std::cout << "\"full_result_space\":3268760,";
    std::cout << "\"feasible_membership_histograms\":" << feasible_histograms << ",";
    std::cout << "\"floor_ge_9_histograms\":" << floor_ge_9_histograms << ",";
    std::cout << "\"floor_ge_10_histograms\":" << floor_ge_10_histograms << ",";
    std::cout << "\"coverage13_optimal_class_histograms\":"
              << coverage13_optimal_class_histograms << ",";
    std::cout << "\"best_membership_histogram\":";
    print_array(best_membership);
    std::cout << ",";
    std::cout << "\"best_metrics\":{";
    std::cout << "\"guaranteed_min_best_hits\":9,";
    std::cout << "\"best_hits_sum\":" << best_metrics.best_hits_sum << ",";
    std::cout << "\"mean_best_hits\":"
              << static_cast<double>(best_metrics.best_hits_sum) / kOutcomeSpace << ",";
    std::cout << "\"best_hits_histogram\":";
    print_histogram(best_metrics.histogram);
    std::cout << ",";
    std::cout << "\"coverage\":{";
    std::cout << "\"11\":" << best_metrics.ge11 << ",";
    std::cout << "\"12\":" << best_metrics.ge12 << ",";
    std::cout << "\"13\":" << best_metrics.ge13 << ",";
    std::cout << "\"14\":" << best_metrics.ge14 << ",";
    std::cout << "\"15\":" << best_metrics.ge15 << "},";
    std::cout << "\"objective_vector\":[9,4,604,19504,237504,1310584,33982067]";
    std::cout << "},";
    std::cout << "\"proof\":{";
    std::cout << "\"symmetry_quotient_complete\":true,";
    std::cout << "\"floor_9_achievable\":true,";
    std::cout << "\"floor_10_impossible\":true,";
    std::cout << "\"coverage14_union_upper_bound\":" << 4 * kSingleCoverage14 << ",";
    std::cout << "\"coverage13_union_upper_bound\":" << 4 * kSingleCoverage13 << ",";
    std::cout << "\"coverage13_upper_bound_achieved\":true,";
    std::cout << "\"coverage12_and_lower_exhausted_inside_prior_optimal_class\":true,";
    std::cout << "\"future_results_used\":false";
    std::cout << "},";
    std::cout << "\"elapsed_seconds\":" << elapsed;
    std::cout << "}\n";
    return 0;
}
