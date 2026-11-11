"""Compare the previous JSON assignment implementation with incremental targets.

Only synthetic object tables are created in a new output directory. The baseline
is loaded from the repository's published pre-optimization commit, not emulated.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.desktop.project import Project, atomic_json
from src.desktop.object_labels import _measurement, RF_PREDICTORS, LABELS_FILENAME
from src.desktop import service


BASELINE_COMMIT = '407af850898759bb35461281e541c7392ef4f776'


def fixture(root, count):
    project = Project.create(root/'project.json', 'SIMULATED labeling benchmark')
    base = root/'tiles'; (base/'overview').mkdir(parents=True)
    manifest = dict(schema_version=3, source_name='simulated', image_shape=[4,4],
                    tiles=[dict(id=1, filename='Tile_001.png')])
    atomic_json(base/'overview/simulated_tiles_coords.json', manifest)
    (base/'Tile_001.png').write_bytes(b'synthetic inclusion marker; not an image')
    output = root/'measurements'/'simulated'/'Measurement_001'; output.mkdir(parents=True)
    csv_path = output/'features.csv'
    with csv_path.open('w',encoding='utf-8',newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['Large_Image','Tile_Name','Object_ID','Class_ID','Class_Name',*RF_PREDICTORS])
        writer.writeheader()
        for ident in range(1,count+1):
            writer.writerow(dict(Large_Image='SIMULATED', Tile_Name='Tile_001', Object_ID=ident,
                Class_ID=-1, Class_Name='Unknown', Area=100, Aspect_Ratio=2, Solidity=.9,
                Euler_Number=1, Endpoints=2, Branch_Points=0))
    run = dict(manifest_signature=service.fingerprint(manifest), annotation_signature=service.content_signature(None), active_tile_ids=[1])
    atomic_json(output/'measurement_run.json', run)
    dataset = dict(id='simulated',name='simulated',path=str(base),results_dir=str(output),
                   last_csv=str(csv_path),measurement_signature=service.fingerprint(run),results_current=True)
    project.datasets.append(dataset); project.save()
    identity = _measurement(dataset)[-1]
    document = dict(schema_version=1,class_catalog_version=2,**identity,labels={
        'Tile_001/'+str(ident): dict(Tile_Name='Tile_001',Object_ID=ident,Manual_Class='fiber',
            Manual_Class_ID=1,Reviewed=True,updated_at='synthetic') for ident in range(1,int(count*.8)+1)})
    atomic_json(output/LABELS_FILENAME, document)
    return project,dataset


def measure(operation):
    start=time.perf_counter(); result=operation()
    return (time.perf_counter()-start)*1000,result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,help='New directory, never an existing project')
    args=parser.parse_args(); root=Path(args.output).resolve(); root.mkdir(parents=True,exist_ok=False)
    source=subprocess.check_output(['git','show',BASELINE_COMMIT+':src/desktop/object_labels.py'],text=True,encoding='utf-8')
    baseline=types.ModuleType('src.desktop.benchmark_previous_labels'); baseline.__package__='src.desktop'
    exec(compile(source,'published_json_label_baseline','exec'),baseline.__dict__)
    results=[]
    for count in (1000,10000,50000):
        old,old_dataset=fixture(root/str(count)/'Previous_JSON',count)
        new,new_dataset=fixture(root/str(count)/'Incremental_SQLite',count)
        legacy=Path(new_dataset['results_dir'])/LABELS_FILENAME
        legacy_sha=hashlib.sha256(legacy.read_bytes()).hexdigest()
        csv_sha=hashlib.sha256(Path(new_dataset['last_csv']).read_bytes()).hexdigest()

        def old_assign(class_key):
            report=baseline.save_object_class(old_dataset,'Tile_001',count,class_key)
            old.add_history('assign_object_class',dataset_id='simulated',object_id=count,class_key=class_key)
            return report

        def new_assign(class_key):
            return service.assign_object_class(new,'simulated','Tile_001',count,class_key,compact=True)

        old_assign('fiber')
        cold,_=measure(lambda:new_assign('fiber'))
        previous,current=[],[]
        for class_key in ('particle','fiber','particle','fiber','particle','fiber','particle'):
            duration,a=measure(lambda:old_assign(class_key)); previous.append(duration)
            duration,b=measure(lambda:new_assign(class_key)); current.append(duration)
            assert a['assigned']==b['assigned'] and a['manual_class']==b['manual_class']
        assert hashlib.sha256(legacy.read_bytes()).hexdigest()==legacy_sha
        assert hashlib.sha256(Path(new_dataset['last_csv']).read_bytes()).hexdigest()==csv_sha
        results.append(dict(objects=count,initial_reviewed=int(count*.8),
            first_import_ms=round(cold,3),previous_json_median_ms=round(statistics.median(previous),3),
            incremental_sqlite_median_ms=round(statistics.median(current),3),
            old_json_samples_ms=[round(x,3) for x in previous],sqlite_samples_ms=[round(x,3) for x in current]))
    report=dict(synthetic=True,baseline_commit=BASELINE_COMMIT,repetitions=7,results=results,
                scope='assignment service only; no Qt rendering or scientific segmentation')
    (root/'Benchmark_results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
