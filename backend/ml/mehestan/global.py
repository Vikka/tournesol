import pandas as pd
import numpy as np
from django.db.models import F, Case, When, Q, QuerySet

from tournesol.models import ContributorRatingCriteriaScore
from core.models import User

from .primitives import BrMean, QrMed, QrUnc, QrDev


W = 5.0

SCALING_WEIGHT_SUPERTRUSTED = W
SCALING_WEIGHT_TRUSTED = 1.0
SCALING_WEIGHT_NONTRUSTED = 0.0

VOTE_WEIGHT_TRUSTED_PUBLIC = 1.0
VOTE_WEIGHT_TRUSTED_PRIVATE = 0.5

TOTAL_VOTE_WEIGHT_NONTRUSTED_DEFAULT = 2.0  # w_⨯,default
TOTAL_VOTE_WEIGHT_NONTRUSTED_FRACTION = 0.1  # f_⨯

# FIXME: Temporary
POLL_NAME = "videos"
CRITERIA_NAME = "largely_recommended"


def get_user_scaling_weights():
    values = (
        User.objects.all()
        .annotate(
            scaling_weight=Case(
                When(
                    pk__in=User.supertrusted_users(), then=SCALING_WEIGHT_SUPERTRUSTED
                ),
                When(pk__in=User.trusted_users(), then=SCALING_WEIGHT_TRUSTED),
                default=SCALING_WEIGHT_NONTRUSTED,
            )
        )
        .values("scaling_weight", user_id=F("pk"))
    )
    return {u["user_id"]: u["scaling_weight"] for u in values}


def get_contributor_criteria_score(
    users: QuerySet[User],
    poll_name: str,
    criteria: str,
    with_voting_weights: bool = False,
):
    queryset = ContributorRatingCriteriaScore.objects.filter(
        contributor_rating__poll__name=poll_name,
        contributor_rating__user__in=users,
        criteria=criteria,
    )

    if with_voting_weights:
        queryset = queryset.annotate(
            voting_weight=Case(
                When(
                    Q(contributor_rating__user__in=User.trusted_users())
                    & Q(contributor_rating__is_public=True),
                    then=VOTE_WEIGHT_TRUSTED_PUBLIC,
                ),
                When(
                    Q(contributor_rating__user__in=User.trusted_users())
                    & Q(contributor_rating__is_public=False),
                    then=VOTE_WEIGHT_TRUSTED_PRIVATE,
                ),
                default=0,  # Vote weight for non-trusted users will be computed separately per entity
            )
        )

    values = queryset.values(
        "score",
        "uncertainty",
        *(["voting_weight"] if with_voting_weights else []),
        user_id=F("contributor_rating__user__pk"),
        uid=F("contributor_rating__entity__uid"),
        is_public=F("contributor_rating__is_public"),
    )
    return pd.DataFrame(values)


def compute_scaling(
    df: pd.DataFrame,
    users_to_compute=None,
    reference_users=None,
    compute_uncertainties=False,
):
    scaling_weights = get_user_scaling_weights()

    def get_significantly_different_pairs(scores: pd.DataFrame):
        # To optimize: this cross product may be expensive in memory
        return (
            scores.merge(scores, how="cross", suffixes=("_a", "_b"))
            .query("uid_a < uid_b")
            .query("abs(score_a - score_b) >= 2*(uncertainty_a + uncertainty_b)")
            .set_index(["uid_a", "uid_b"])
        )

    if users_to_compute is None:
        users_to_compute = df.user_id.unique()

    if reference_users is None:
        reference_users = df.user_id.unique()

    s_dict = {}
    delta_s_dict = {}
    for user_n in users_to_compute:
        user_scores = df[df.user_id == user_n].drop("user_id", axis=1)
        s_nqm = []
        delta_s_nqm = []
        s_weights = []
        for user_m in (u for u in reference_users if u != user_n):
            m_scores = df[df.user_id == user_m].drop("user_id", axis=1)
            common_uids = set(user_scores.uid).intersection(m_scores.uid)

            m_scores = m_scores[m_scores.uid.isin(common_uids)]
            n_scores = user_scores[user_scores.uid.isin(common_uids)]

            ABn = get_significantly_different_pairs(n_scores)
            ABm = get_significantly_different_pairs(m_scores)
            ABnm = ABn.join(ABm, how="inner", lsuffix="_n", rsuffix="_m")
            if len(ABnm) == 0:
                continue
            s_nqmab = np.abs(ABnm.score_a_m - ABnm.score_b_m) / np.abs(
                ABnm.score_a_n - ABnm.score_b_n
            )

            # To check: is it correct to subtract s_nqmab?
            delta_s_nqmab = (
                (
                    np.abs(ABnm.score_a_m - ABnm.score_b_m)
                    + ABnm.uncertainty_a_m
                    + ABnm.uncertainty_b_m
                )
                / (
                    np.abs(ABnm.score_a_n - ABnm.score_b_n)
                    - ABnm.uncertainty_a_n
                    - ABnm.uncertainty_b_n
                )
            ) - s_nqmab

            s = QrMed(1, 1, s_nqmab, delta_s_nqmab)
            s_nqm.append(s)
            delta_s_nqm.append(QrUnc(1, 1, 1, s_nqmab, delta_s_nqmab, qr_med=s))
            s_weights.append(scaling_weights[user_m])

        s_weights = np.array(s_weights)
        theta_inf = np.max(user_scores.score.abs())
        s_nqm = np.array(s_nqm)
        delta_s_nqm = np.array(delta_s_nqm)
        if compute_uncertainties:
            qr_med = QrMed(8 * W * theta_inf, s_weights, s_nqm - 1, delta_s_nqm)
            s_dict[user_n] = 1 + qr_med
            delta_s_dict[user_n] = QrUnc(
                8 * W * theta_inf, s_weights, s_nqm - 1, delta_s_nqm, qr_med=qr_med
            )
        else:
            s_dict[user_n] = 1 + BrMean(
                8 * W * theta_inf, s_weights, s_nqm - 1, delta_s_nqm
            )

    tau_dict = {}
    delta_tau_dict = {}
    for user_n in users_to_compute:
        user_scores = df[df.user_id == user_n].drop("user_id", axis=1)
        tau_nqm = []
        delta_tau_nqm = []
        s_weights = []
        for user_m in (u for u in reference_users if u != user_n):
            m_scores = df[df.user_id == user_m].drop("user_id", axis=1)
            common_uids = set(user_scores.uid).intersection(m_scores.uid)

            if len(common_uids) == 0:
                continue

            m_scores = m_scores[m_scores.uid.isin(common_uids)]
            n_scores = user_scores[user_scores.uid.isin(common_uids)]

            tau_nqmab = (
                s_dict[user_m] * m_scores.score - s_dict[user_n] * n_scores.score
            )
            delta_tau_nqmab = (
                s_dict[user_n] * n_scores.uncertainty
                + s_dict[user_m] * m_scores.uncertainty
            )
            tau = QrMed(1, 1, tau_nqmab, delta_tau_nqmab)
            tau_nqm.append(tau)
            delta_tau_nqm.append(QrUnc(1, 1, 1, tau_nqmab, delta_tau_nqmab, qr_med=tau))
            s_weights.append(scaling_weights[user_m])

        s_weights = np.array(s_weights)
        tau_nqm = np.array(tau_nqm)
        delta_tau_nqm = np.array(delta_tau_nqm)
        if compute_uncertainties:
            qr_med = QrMed(8 * W, s_weights, tau_nqm, delta_tau_nqm)
            tau_dict[user_n] = qr_med
            delta_tau_dict[user_n] = QrUnc(
                8 * W, 1, s_weights, tau_nqm, delta_tau_nqm, qr_med=qr_med
            )
        else:
            tau_dict[user_n] = BrMean(8 * W, s_weights, tau_nqm, delta_tau_nqm)

    return pd.DataFrame(
        {
            "s": s_dict,
            "tau": tau_dict,
            **(
                {"delta_s": delta_s_dict, "delta_tau": delta_tau_dict}
                if compute_uncertainties
                else {}
            ),
        }
    )


def get_scaling_for_supertrusted():
    df = get_contributor_criteria_score(
        User.supertrusted_users(), poll_name=POLL_NAME, criteria=CRITERIA_NAME
    )
    return compute_scaling(df)


def get_scaled_scores():
    supertrusted_scaling = get_scaling_for_supertrusted()

    df = get_contributor_criteria_score(
        User.objects.all(),
        poll_name=POLL_NAME,
        criteria=CRITERIA_NAME,
        with_voting_weights=True,
    )

    df = df.join(supertrusted_scaling, on="user_id")
    df["s"].fillna(1, inplace=True)
    df["tau"].fillna(0, inplace=True)
    df["score"] = df["s"] * df["score"] + df["tau"]
    df["uncertainty"] *= df["s"]
    df.drop(["s", "tau"], axis=1, inplace=True)

    non_supertrusted = User.objects.exclude(
        pk__in=User.supertrusted_users()
    ).values_list("pk", flat=True)
    trusted_and_supertrusted = (
        User.objects.filter(
            Q(pk__in=User.supertrusted_users()) | Q(pk__in=User.trusted_users())
        )
        .distinct()
        .values_list("pk", flat=True)
    )

    non_supertrusted_scaling = compute_scaling(
        df,
        users_to_compute=non_supertrusted,
        reference_users=trusted_and_supertrusted,
        compute_uncertainties=True,
    )

    df = df.join(non_supertrusted_scaling, on="user_id")
    df["s"].fillna(1, inplace=True)
    df["tau"].fillna(0, inplace=True)
    df["delta_s"].fillna(0, inplace=True)
    df["delta_tau"].fillna(0, inplace=True)
    df["uncertainty"] = (
        df["s"] * df["uncertainty"]
        + df["delta_s"] * df["score"].abs()
        + df["delta_tau"]
    )
    df["score"] = df["score"] * df["s"] + df["tau"]
    df.drop(["s", "tau", "delta_s", "delta_tau"], axis=1, inplace=True)

    global_scores = {}
    for (uid, scores) in df.groupby("uid"):
        trusted_weight = scores["voting_weight"].sum()
        non_trusted_weight = (
            TOTAL_VOTE_WEIGHT_NONTRUSTED_DEFAULT
            + TOTAL_VOTE_WEIGHT_NONTRUSTED_FRACTION * trusted_weight
        )
        nb_non_trusted_public = (
            scores["is_public"] & (scores["voting_right"] == 0)
        ).sum()
        nb_non_trusted_private = (
            ~scores["is_public"] & (scores["voting_right"] == 0)
        ).sum()

        scores["voting_weight"].mask(
            scores["is_public"] & (scores["voting_right"] == 0),
            min(
                VOTE_WEIGHT_TRUSTED_PUBLIC,
                2
                * non_trusted_weight
                / (2 * nb_non_trusted_public + nb_non_trusted_private),
            ),
            inplace=True,
        )
        scores["voting_weight"].mask(
            ~scores["is_public"] & (scores["voting_right"] == 0),
            min(
                VOTE_WEIGHT_TRUSTED_PRIVATE,
                non_trusted_weight
                / (2 * nb_non_trusted_public + nb_non_trusted_private),
            ),
            inplace=True,
        )

        w = scores.voting_weight
        theta = scores.score
        delta = scores.uncertainty
        rho = QrMed(2 * W, w, theta, delta)
        rho_uncertainty = QrUnc(2 * W, 1, w, theta, delta, qr_med=rho)
        rho_deviation = QrDev(2 * W, 1, w, theta, delta, qr_med=rho)
        global_scores[uid] = {
            "score": rho,
            "uncertainty": rho_uncertainty,
            "deviation": rho_deviation,
        }

    return pd.DataFrame(global_scores)
