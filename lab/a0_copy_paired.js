// Run in the functions.exec orchestration runtime, not Node or a phone.
// Supply root/cases through store("a0_copy_matrix_root", ...) and
// store("a0_copy_matrix_cases", ...). The plan uses Python Random(210090).
const root = load('a0_copy_matrix_root');
const cases = load('a0_copy_matrix_cases');
if (typeof root !== 'string' || !Array.isArray(cases) || cases.length !== 30) throw Error('matrix inputs missing');
const observations = [];
const quote = value => "'"+value.replaceAll("'", "'\\''")+"'";
for (const trial of cases) {
  if (!['.ko','.bin'].includes(trial.suffix) || !/^case-\d\d$/.test(trial.id)) throw Error('bad trial');
  const active = 'build/a0-b-paired/active/payload'+trial.suffix;
  const report = 'build/a0-b-paired/cases/'+trial.id+'.json';
  const clean = 'from pathlib import Path; Path('+JSON.stringify(active)+').unlink(missing_ok=True)';
  const command = 'python3 -c '+quote(clean)+' && python3 scripts/capture_a0_copy_probe.py --source build/a0-b-paired/source.bin --target '+quote(active)+' --report '+quote(report);
  let writer = await tools.exec_command({cmd:command,workdir:root,yield_time_ms:1000,max_output_tokens:1500});
  let second = null;
  if (trial.condition !== 'serial') {
    if (!writer.session_id) throw Error('writer exited before planned overlap');
    if (trial.condition.startsWith('after_')) await new Promise(resolve=>setTimeout(resolve,3000));
    const note = 'build/a0-b-paired/cases/'+trial.id+'.note';
    const program = 'import time,json; from pathlib import Path; started=time.monotonic_ns(); time.sleep(4); '+
      (trial.condition.endsWith('_note')?'Path('+JSON.stringify(note)+').write_text("unrelated note\\n"); ':'')+
      'print(json.dumps(dict(started_monotonic_ns=started,ended_monotonic_ns=time.monotonic_ns(),payload_opened_by_program=False)))';
    const run = await tools.exec_command({cmd:'python3 -c '+quote(program),workdir:root,yield_time_ms:10000,max_output_tokens:500});
    if (run.session_id || run.exit_code !== 0) throw Error('second program did not complete');
    second = JSON.parse(run.output.trim());
  }
  while (writer.session_id) writer = await tools.write_stdin({session_id:writer.session_id,chars:'',yield_time_ms:1000,max_output_tokens:1500});
  const read = await tools.exec_command({cmd:'python3 -c '+quote('from pathlib import Path; print(Path('+JSON.stringify(report)+').read_text())'),workdir:root,max_output_tokens:12000});
  if (read.exit_code !== 0 || writer.exit_code !== 0) throw Error('probe report incomplete');
  const probe = JSON.parse(read.output);
  const phase = !second || (trial.condition.startsWith('during_')?
    second.started_monotonic_ns >= probe.write_started_monotonic_ns && second.started_monotonic_ns < probe.write_closed_monotonic_ns:
    second.started_monotonic_ns >= probe.immediate.read_completed_monotonic_ns && second.started_monotonic_ns < probe.later.monotonic_ns);
  observations.push({trial,second,phase_adhered:phase,probe});
  store('a0_copy_matrix_observations',observations);
  notify({completed:observations.length,total:cases.length,condition:trial.condition,suffix:trial.suffix,phase_adhered:phase,immediate_ok:probe.immediate.matches,later_ok:probe.later.matches,later_bytes:probe.later.bytes});
}
text({completed:observations.length,late_changes:observations.filter(r=>!r.probe.later.matches).length,missed_phase:observations.filter(r=>!r.phase_adhered).length});
