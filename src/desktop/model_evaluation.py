"""Source-group and stratified object holdouts with training-only tuning."""

from collections import Counter, defaultdict
from itertools import combinations
import random
from time import perf_counter

from src.app_settings import PipelineCancelled
from src.default_settings import MODEL_DEFAULTS
from src.object_classes import OBJECT_CLASS_CATALOG
from .i18n import tr

CLASS_IDS = tuple(entry['id'] for entry in OBJECT_CLASS_CATALOG)
FOREST_TREE_COUNT_RANGE = (1, 2000)


def _check_cancel(cancelled):
    if cancelled and cancelled():
        raise PipelineCancelled(tr('Обработка остановлена пользователем.'))


def _counts(targets):
    counts = Counter(targets)
    return {str(label): counts[label] for label in CLASS_IDS}


def _validation_folds(rows, targets, train, train_groups, folds, seed, cancelled):
    """Construct stratified group folds and verify the class support of each fit."""
    from sklearn.model_selection import StratifiedGroupKFold

    train_targets = [targets[i] for i in train]
    totals = Counter(train_targets)
    # sklearn cannot construct K stratified folds when every class has fewer
    # than K objects. Another holdout may leave enough objects for validation.
    if max(totals.values()) < folds:
        return None

    best, best_key = None, None
    rng = random.Random(seed)
    # In sklearn 1.7.2, shuffle=True permutes the group histograms without
    # remapping their IDs before the fold indices are returned. Permuting the
    # group IDs instead preserves the mapping and varies the greedy tie order.
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=False)
    for _ in range(12):
        _check_cancel(cancelled)
        ranks = {name: i for i, name in enumerate(rng.sample(train_groups, len(train_groups)))}
        encoded = [ranks[rows[i]['group']] for i in train]
        candidate = []
        for a, b in splitter.split(train, train_targets, encoded):
            # sklearn returns positions in the training slice. Store global
            # snapshot indices so the same matrix serves the holdout and CV.
            fit, validation = [train[i] for i in a], [train[i] for i in b]
            val_counts = Counter(targets[i] for i in validation)
            if not validation or any(val_counts[label] == count for label, count in totals.items()):
                break
            candidate.append(dict(train=fit, test=validation,
                                  train_counts=_counts(targets[i] for i in fit),
                                  test_counts=_counts(targets[i] for i in validation)))
        if len(candidate) != folds:
            continue
        # Evaluate the actual fold assignment. Prefer validation coverage, then
        # equal proportions of each class and balanced numbers of objects.
        key = (sum(fold['test_counts'][str(label)] == 0 for fold in candidate for label in totals),
               sum(abs(fold['test_counts'][str(label)] / count - 1 / folds)
                   for fold in candidate for label, count in totals.items()),
               sum(abs(len(fold['test']) / len(train) - 1 / folds) for fold in candidate))
        if best_key is None or key < best_key:
            best, best_key = candidate, key
    return best


def _object_plan(rows, targets, seed, folds, cancelled):
    """Keep each class near a 20% holdout while respecting integer counts."""
    by_class = defaultdict(list)
    for index, target in enumerate(targets):
        by_class[target].append(index)
    classes = sorted(by_class)
    totals = {label: len(by_class[label]) for label in classes}
    minimum_train = folds or 1
    if min(totals.values()) < minimum_train:
        raise ValueError(tr('Object K-fold needs at least K training objects in each class. Reduce K or select other classes.'))
    upper = {label: count - minimum_train for label, count in totals.items()}
    lower = {label: int(upper[label] > 0) for label in classes}
    if not sum(upper.values()):
        raise ValueError(tr('No test objects remain after reserving training examples for every class.'))

    # Round each class near a fifth and clamp it to feasible bounds. Then
    # reconcile the total using whichever integer step best matches its quota.
    # A singleton stays in training, and a class with spare support gets at
    # least one test example even when 20% rounds to zero.
    allocation = {label: max(lower[label], min(upper[label], (totals[label] + 2) // 5))
                  for label in classes}
    target_size = max(sum(lower.values()), min(sum(upper.values()), (len(rows) + 2) // 5))
    difference = target_size - sum(allocation.values())
    while difference > 0:
        label = max((label for label in classes if allocation[label] < upper[label]),
                    key=lambda label: totals[label] - 5 * allocation[label])
        allocation[label] += 1
        difference -= 1
    while difference < 0:
        label = max((label for label in classes if allocation[label] > lower[label]),
                    key=lambda label: 5 * allocation[label] - totals[label])
        allocation[label] -= 1
        difference += 1

    rng = random.Random(seed)
    train, test = [], []
    for label in classes:
        _check_cancel(cancelled)
        indices = by_class[label]
        rng.shuffle(indices)
        boundary = allocation[label]
        test.extend(indices[:boundary])
        train.extend(indices[boundary:])
    train.sort()
    test.sort()

    cv = []
    if folds:
        from sklearn.model_selection import StratifiedKFold

        splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
        for a, b in splitter.split(train, [targets[i] for i in train]):
            _check_cancel(cancelled)
            fit, validation = [train[i] for i in a], [train[i] for i in b]
            cv.append(dict(train=fit, test=validation, train_counts=_counts(targets[i] for i in fit),
                           test_counts=_counts(targets[i] for i in validation)))
    return dict(train=train, test=test, train_groups=sorted({rows[i]['group'] for i in train}),
                test_groups=sorted({rows[i]['group'] for i in test}), folds=cv,
                train_counts=_counts(targets[i] for i in train), test_counts=_counts(targets[i] for i in test),
                demo=False, test_fraction=len(test) / len(rows), seed=seed, split_mode='object')


def plan_split(rows, seed=42, folds=0, cancelled=None, split_mode=MODEL_DEFAULTS['split_mode']):
    """Return snapshot row indices for a holdout and optional CV folds.

    Group membership is decided upstream from source/experiment provenance.
    The default uses entire groups. Explicit object mode checks held-out rows
    on this input only and can place the same source in both partitions.
    """
    if split_mode not in ('group', 'object'):
        raise ValueError(tr('Select a supported split method.'))
    if not rows:
        raise ValueError(tr('Select datasets with reviewed objects and confirmed sources.'))
    targets = [row['target'] for row in rows]
    classes = set(targets)
    if len(classes) < 2:
        raise ValueError(tr('Model comparison needs at least two reviewed classes.'))
    if split_mode == 'object':
        return _object_plan(rows, targets, seed, folds, cancelled)
    groups = {}
    for index, row in enumerate(rows):
        groups.setdefault(row['group'], []).append(index)
    names = sorted(groups)
    all_indices = list(range(len(rows)))
    if len(names) == 1:
        if folds:
            raise ValueError(tr('Cross-validation needs multiple training groups.'))
        return dict(train=all_indices, test=[], train_groups=names, test_groups=[], folds=[],
                    train_counts=_counts(targets), test_counts=_counts([]), demo=True,
                    test_fraction=0, seed=seed, split_mode='group')
    if folds and (folds < 2 or folds >= len(names)):
        raise ValueError(tr('Cross-validation needs at least K independent training groups.'))
    group_counts = {name: Counter(targets[i] for i in indices) for name, indices in groups.items()}
    totals = Counter(targets)
    group_support = Counter(label for counts in group_counts.values() for label in counts)
    if folds and min(group_support.values()) < 2:
        raise ValueError(tr('Cross-validation needs each class in at least two training groups.'))
    best = None
    best_key = None
    cv_candidates = {}
    rng = random.Random(seed)
    order = rng.sample(names, len(names))
    rank = {name: index for index, name in enumerate(order)}

    def consider(test_groups, counts):
        nonlocal best, best_key
        # Require every reviewed class in training. Within two percentage points
        # of the 20% test share, prefer coverage of more classes in the test set.
        if any(counts[label] >= totals[label] for label in classes):
            return
        size = sum(counts.values())
        distance = abs(size / len(rows) - 0.20)
        coverage = sum(counts[label] == 0 for label in classes)
        # Give each class equal influence when comparing its test share with
        # the 20% target. Raw counts would let the largest classes dominate.
        imbalance = sum(abs(counts[label] / totals[label] - .20) for label in classes)
        key = (max(0, distance - .02), coverage, imbalance, distance,
               tuple(sorted(rank[name] for name in test_groups)))
        if best_key is None or key < best_key:
            best_key, best = key, tuple(test_groups)
        # A feasible holdout must leave K groups and at least two groups per
        # class for CV. Rank eligible holdouts by the same label/count criteria
        # and verify the actual folds before choosing one. No estimator is fit
        # and no test predictions are used during split planning.
        if folds and len(names) - len(test_groups) >= folds:
            if all(group_support[label] - sum(label in group_counts[name] for name in test_groups) >= 2
                   for label in classes):
                cv_candidates[frozenset(test_groups)] = key

    if len(names) <= 10:
        for size in range(1, len(names)):
            for subset in combinations(names, size):
                counts = Counter()
                for name in subset:
                    counts.update(group_counts[name])
                consider(subset, counts)
    else:
        # Enumerating every subset is exponential. Score single groups and
        # seeded prefixes of shuffled groups when the project has many groups.
        for name in names:
            consider([name], group_counts[name])
        for _ in range(256):
            _check_cancel(cancelled)
            order = names.copy()
            rng.shuffle(order)
            counts = Counter()
            for end, name in enumerate(order[:-1], 1):
                counts.update(group_counts[name])
                consider(order[:end], counts)
                if sum(counts.values()) / len(rows) >= .25:
                    break
    if best is None:
        raise ValueError(tr('No group holdout can keep all reviewed classes in training.'))
    cv = []
    if folds:
        for candidate in sorted(cv_candidates, key=cv_candidates.get):
            _check_cancel(cancelled)
            training_groups = sorted(set(names) - candidate)
            indices = [i for i in all_indices if rows[i]['group'] not in candidate]
            cv = _validation_folds(rows, targets, indices, training_groups, folds, seed, cancelled)
            if cv:
                best = candidate
                break
        if not cv:
            raise ValueError(tr('No group holdout supports these folds with every class in each training fold.'))
    test_groups = set(best)
    train = [i for i in all_indices if rows[i]['group'] not in test_groups]
    test = [i for i in all_indices if rows[i]['group'] in test_groups]
    train_groups = sorted(set(names) - test_groups)
    return dict(train=train, test=test, train_groups=train_groups, test_groups=sorted(test_groups),
                folds=cv, train_counts=_counts(targets[i] for i in train),
                test_counts=_counts(targets[i] for i in test), demo=False,
                test_fraction=len(test) / len(rows), seed=seed, split_mode='group')


def evaluate(rows, features, plan, progress=None, cancelled=None, save_model=None,
             forest_tree_count=MODEL_DEFAULTS['forest_tree_count']):
    """Select hyperparameters on training folds and score the final fits on holdout."""
    import numpy as np
    import sklearn
    from sklearn.dummy import DummyClassifier
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import confusion_matrix, f1_score
    from sklearn.tree import DecisionTreeClassifier, export_text

    x = np.asarray([row['values'] for row in rows], dtype=float)
    y = np.asarray([row['target'] for row in rows], dtype=int)
    train, test = plan['train'], plan['test']
    test_positions = defaultdict(list)
    for position, index in enumerate(test):
        test_positions[rows[index]['group']].append(position)
    # Unfiltered comparisons retain the stable catalog order. An explicit
    # subset uses the same order restricted to the selected class IDs.
    classes = plan.get('classes', CLASS_IDS)
    supported = sorted(set(y[test].tolist()))
    factories = {
        'dummy': (DummyClassifier, [dict(strategy='most_frequent')]),
        # Compare the same limits for both criteria. The catalog order
        # supplies the fixed settings and breaks exact validation-score ties.
        'tree': (DecisionTreeClassifier, [
            dict(max_depth=depth, min_samples_leaf=leaf, criterion=criterion)
            for criterion in MODEL_DEFAULTS['split_criteria']
            for depth, leaf in MODEL_DEFAULTS['tree_candidate_limits']]),
        'forest': (RandomForestClassifier, [
            dict(n_estimators=forest_tree_count, max_features=features_per_split, max_depth=depth,
                 min_samples_leaf=leaf, criterion=criterion)
            for criterion in MODEL_DEFAULTS['split_criteria']
            for features_per_split, depth, leaf in MODEL_DEFAULTS['forest_candidate_limits']]),
    }
    keys = ('tree', 'forest') if plan['demo'] else tuple(factories)
    total = sum(1 + (len(factories[key][1]) * len(plan['folds']) if key != 'dummy' else 0) for key in keys)
    done = 0
    report = dict(models={}, predictions=[dict(rows[i], predicted={}) for i in test],
                  classes=list(classes), split_mode=plan.get('split_mode', 'group'),
                  runtime={'scikit-learn': sklearn.__version__})
    for key in keys:
        factory, candidates = factories[key]
        best = candidates[0]
        tuning = []
        cv_fit_seconds = 0.0
        if plan['folds'] and key != 'dummy':
            for candidate in candidates:
                predicted, truth, fold_scores = [], [], []
                for fold in plan['folds']:
                    _check_cancel(cancelled)
                    model = factory(random_state=plan['seed'], **candidate)
                    fit_x, fit_y = x[fold['train']], y[fold['train']]
                    started = perf_counter()
                    model.fit(fit_x, fit_y)
                    cv_fit_seconds += perf_counter() - started
                    validation_y = y[fold['test']]
                    validation_predicted = model.predict(x[fold['test']])
                    predicted.extend(validation_predicted.tolist())
                    truth.extend(validation_y.tolist())
                    fold_scores.append(float(f1_score(validation_y, validation_predicted,
                                                      average='macro', zero_division=0)))
                    done += 1
                    if progress:
                        progress(done, total)
                # Pool predictions across folds so macro F1 uses a single
                # confusion matrix even when the validation folds differ in size.
                score = float(f1_score(truth, predicted, average='macro', zero_division=0))
                tuning.append(dict(parameters=candidate, macro_f1=score, fold_macro_f1=fold_scores))
            best = max(tuning, key=lambda result: result['macro_f1'])['parameters']
        _check_cancel(cancelled)
        model = factory(random_state=plan['seed'], **best)
        fit_x, fit_y = x[train], y[train]
        started = perf_counter()
        model.fit(fit_x, fit_y)
        final_fit_seconds = perf_counter() - started
        result = dict(parameters=best, tuning=tuning)
        if key in ('tree', 'forest'):
            # Time only estimator fitting, so scoring, permutation shuffles,
            # I/O and serialization do not inflate the training measurement.
            info = dict(final_fit_seconds=final_fit_seconds, cv_fit_seconds=cv_fit_seconds,
                        cv_fit_count=len(tuning) * len(plan['folds']))
            if key == 'tree':
                info['depth'] = model.get_depth()
            else:
                depths = [tree.get_depth() for tree in model.estimators_]
                info.update(tree_count=len(depths), min_depth=min(depths), max_depth=max(depths))
            result['fit_info'] = info
        report['models'][key] = result
        if save_model and key != 'dummy':
            result['artifact'] = save_model(key, model)
        if test:
            predicted = model.predict(x[test])
            matrix = confusion_matrix(y[test], predicted, labels=classes)
            result['confusion'] = matrix.tolist()
            result['macro_f1'] = float(f1_score(y[test], predicted, labels=supported, average='macro', zero_division=0))
            result['groups'] = {}
            for name, selected in test_positions.items():
                result['groups'][name] = float(f1_score(y[test][selected], predicted[selected],
                    labels=sorted(set(y[test][selected].tolist())), average='macro', zero_division=0))
            for row, label in zip(report['predictions'], predicted.tolist()):
                row['predicted'][key] = label
            if key == 'forest':
                # Report importance on held-out data after model selection.
                def score(estimator, values, labels):
                    _check_cancel(cancelled)
                    return f1_score(labels, estimator.predict(values), labels=supported,
                                    average='macro', zero_division=0)

                importance = permutation_importance(model, x[test], y[test], scoring=score,
                                                    n_repeats=5, random_state=plan['seed'])
                result['permutation_importance'] = [
                    dict(feature=feature, mean=float(mean), std=float(std))
                    for feature, mean, std in zip(features, importance.importances_mean, importance.importances_std)]
        if key == 'tree':
            report['tree'] = export_text(model, feature_names=features, decimals=5, show_weights=True)
            node_groups = [set() for _ in range(model.tree_.node_count)]
            for i, indices in zip(train, model.decision_path(x[train])):
                for node in indices.indices:
                    node_groups[node].add(rows[i]['group'])
            report['tree_nodes'] = []
            depths = [0] * model.tree_.node_count
            for node, groups in enumerate(node_groups):
                tree = model.tree_
                feature = tree.feature[node]
                count = int(tree.n_node_samples[node])
                class_counts = {str(int(label)): round(float(value) * count)
                                for label, value in zip(model.classes_, tree.value[node, 0])}
                left, right = int(tree.children_left[node]), int(tree.children_right[node])
                if feature >= 0:
                    depths[left] = depths[right] = depths[node] + 1
                report['tree_nodes'].append(dict(node=node, objects=count, groups=len(groups),
                    depth=depths[node], left=left if feature >= 0 else None,
                    right=right if feature >= 0 else None,
                    predicted=int(model.classes_[np.argmax(tree.value[node, 0])]),
                    classes=class_counts, feature=features[feature] if feature >= 0 else None,
                    threshold=float(tree.threshold[node]) if feature >= 0 else None))
            if test:
                # Reconstruct the displayed path using the input precision of
                # sklearn's tree traversal, including threshold equality.
                for row, indices in zip(report['predictions'], model.decision_path(x[test])):
                    path = []
                    for node in indices.indices:
                        feature = model.tree_.feature[node]
                        if feature >= 0:
                            threshold = float(model.tree_.threshold[node])
                            path.append(dict(node=int(node), feature=features[feature], threshold=threshold,
                                             left=bool(np.float32(row['values'][feature]) <= threshold)))
                    row['tree_path'] = path
        done += 1
        if progress:
            progress(done, total)
    _check_cancel(cancelled)
    return report
