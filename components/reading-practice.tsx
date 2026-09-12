'use client';
import {useEffect,useRef,useState} from 'react';
import {Mic,Square,LoaderCircle} from 'lucide-react';
import {Button} from '@/components/ui/button';
export type ReadingResult={id:string;score:number;matched:number;expectedCount:number;recognizedCount:number;duration:number;transcript:string;createdAt:string;audioUrl:string;details:{kind:string;expected:string;heard:string}[]};
function wavBytes(samples:Float32Array){
 const buffer=new ArrayBuffer(44+samples.length*2),v=new DataView(buffer);const text=(at:number,s:string)=>{for(let i=0;i<s.length;i++)v.setUint8(at+i,s.charCodeAt(i));};
 text(0,'RIFF');v.setUint32(4,36+samples.length*2,true);text(8,'WAVE');text(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,16000,true);v.setUint32(28,32000,true);v.setUint16(32,2,true);v.setUint16(34,16,true);text(36,'data');v.setUint32(40,samples.length*2,true);
 for(let i=0;i<samples.length;i++){const s=Math.max(-1,Math.min(1,samples[i]));v.setInt16(44+i*2,s<0?s*32768:s*32767,true);}return buffer;
}
export default function ReadingPractice({articleId,history,onSaved,sourceId,onRecorded}:{articleId:string;history:ReadingResult[];onSaved:()=>Promise<unknown>;sourceId?:string;onRecorded?:(value:ReadingResult)=>void}){
 const [status,setStatus]=useState<'idle'|'starting'|'recording'|'scoring'|'finishing'>('idle'),[error,setError]=useState(''),[seconds,setSeconds]=useState(0),[level,setLevel]=useState(0),[blob,setBlob]=useState<Blob|null>(null),[url,setUrl]=useState(''),[result,setResult]=useState<ReadingResult|null>(history.at(-1)||null);
 const context=useRef<AudioContext|null>(null),stream=useRef<MediaStream|null>(null),node=useRef<AudioWorkletNode|null>(null),source=useRef<MediaStreamAudioSourceNode|null>(null),chunks=useRef<Float32Array[]>([]),timer=useRef<ReturnType<typeof setInterval>|null>(null),timeout=useRef<ReturnType<typeof setTimeout>|null>(null),alive=useRef(true),recordingId=useRef(''),finishRef=useRef<()=>void>(()=>{}),captureVersion=useRef(0),finishing=useRef(false);
 function release(){stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;node.current?.disconnect();source.current?.disconnect();void context.current?.close();context.current=null;node.current=null;source.current=null;if(timer.current)clearInterval(timer.current);if(timeout.current)clearTimeout(timeout.current);timer.current=null;timeout.current=null;}
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;captureVersion.current++;release();};},[]);
 useEffect(()=>{if(!blob){setUrl('');return;}const u=URL.createObjectURL(blob);setUrl(u);return()=>URL.revokeObjectURL(u);},[blob]);
 useEffect(()=>{if(history.length)setResult(history[history.length-1]);},[history]);
 async function start(){
  setError('');if(!navigator.mediaDevices?.getUserMedia){setError('当前浏览器无法使用麦克风，请用 Edge 或 Chrome 打开本地网页。');return;}
  const token=++captureVersion.current;setStatus('starting');window.dispatchEvent(new Event('vocab-stop-speech'));
  try{const media=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});if(!alive.current||token!==captureVersion.current){media.getTracks().forEach(t=>t.stop());return;}stream.current=media;
   const ctx=new AudioContext({sampleRate:16000});context.current=ctx;if(ctx.sampleRate!==16000)throw Error('浏览器不支持 16kHz 录音，请使用 Edge 或 Chrome。');await ctx.audioWorklet.addModule('/recording-worklet.js');await ctx.resume();
   if(!alive.current||token!==captureVersion.current){release();return;}
   const recorder=new AudioWorkletNode(ctx,'local-reading-recorder');node.current=recorder;source.current=ctx.createMediaStreamSource(media);const silent=ctx.createGain();silent.gain.value=0;source.current.connect(recorder);recorder.connect(silent);silent.connect(ctx.destination);
   chunks.current=[];recordingId.current=crypto.randomUUID().replaceAll('-','');setBlob(null);setSeconds(0);setResult(null);setStatus('recording');
   recorder.port.onmessage=e=>{if(e.data instanceof Float32Array){chunks.current.push(e.data);let sum=0;for(const x of e.data)sum+=x*x;setLevel(Math.min(100,Math.sqrt(sum/e.data.length)*450));}};
   const started=Date.now();timer.current=setInterval(()=>setSeconds(Math.floor((Date.now()-started)/1000)),500);timeout.current=setTimeout(()=>finishRef.current(),300000);
  }catch(e){release();if(alive.current){setStatus('idle');setError(e instanceof Error?(e.name==='NotAllowedError'?'未获得麦克风权限，请在浏览器允许访问麦克风后重试。':e.message):'无法开始录音');}}
 }
 async function finish(){
  if(finishing.current||!node.current)return;finishing.current=true;setStatus('finishing');
  source.current?.disconnect();stream.current?.getTracks().forEach(t=>t.stop());
  if(node.current){const recorder=node.current;await new Promise<void>(resolve=>{const t=setTimeout(resolve,1200);recorder.port.onmessage=e=>{if(e.data==='flushed'){clearTimeout(t);resolve();}else if(e.data instanceof Float32Array)chunks.current.push(e.data);};recorder.port.postMessage('flush');});}
  const length=chunks.current.reduce((n,c)=>n+c.length,0);const samples=new Float32Array(length);let at=0;for(const chunk of chunks.current){samples.set(chunk,at);at+=chunk.length;}chunks.current=[];release();finishing.current=false;if(!alive.current)return;
  setStatus('idle');setLevel(0);if(length<32000){setError('录音不足 2 秒，请重新朗读。');return;}setBlob(new Blob([wavBytes(samples)],{type:'audio/wav'}));setSeconds(Math.round(length/16000));
 }
 finishRef.current=()=>{void finish();};
 async function score(){
  if(!blob)return;setStatus('scoring');setError('');
  try{const data=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('无法读取录音'));reader.readAsDataURL(blob);});
   const response=await fetch('/api/reading',{method:'POST',headers:{'Content-Type':'application/json','X-Local-App':'vocab'},body:JSON.stringify({articleId,sourceId,mode:onRecorded?'retell':'reading',recordingId:recordingId.current,audio:data})});const r=await response.json() as ReadingResult&{error?:string};if(!response.ok)throw Error(r.error||'本地评分失败');if(alive.current){if(onRecorded)onRecorded(r);else setResult(r);}await onSaved();
  }catch(e){if(alive.current)setError((e instanceof Error?e.message:'评分未完成')+'。录音仍可回听或再次提交。');}finally{if(alive.current)setStatus('idle');}
 }
 return <section className="reading-practice"><h4>{onRecorded?'录下你的复述':'轮到你朗读'}</h4><p>{onRecorded?'用自己的英语表达原意。录音在本地转成文字，下一步确认文字后交给 AI。':'对照上方原文朗读，结束后提交本地评分。录音不会发送给外部 API。'}</p><div className="record-actions">
  {status==='recording'?<Button onClick={finish}><Square/>结束录音</Button>:<Button variant="outline" disabled={status!=='idle'} onClick={start}><Mic/>{status==='starting'?'正在打开麦克风…':blob?'重新录制':onRecorded?'开始本人复述':'开始本人朗读'}</Button>}
  {status==='starting'&&<Button variant="ghost" onClick={()=>{captureVersion.current++;release();setStatus('idle');}}>取消</Button>}
  <span role="status">{status==='recording'?`正在录音 ${seconds} 秒 / 最长 5 分钟`:status==='scoring'?(onRecorded?'正在本地识别复述…':'正在本地识别与评分…'):blob?`录音 ${seconds} 秒`:''}</span>
  {blob&&<Button disabled={status!=='idle'} onClick={score}>{status==='scoring'&&<LoaderCircle className="spin"/>}{onRecorded?'识别复述录音':'提交本地评分'}</Button>}
 </div>{status==='recording'&&<div className="record-meter" aria-label="麦克风音量"><span style={{width:`${level}%`}}/></div>}
 {url&&<audio controls src={url} className="article-audio" aria-label="回听本人录音"/>}
 {error&&<p role="alert" className="record-error">{error}</p>}
 {result&&<div className="reading-result"><strong>{result.score}<small> / 100 · 文本匹配评分</small></strong><p>匹配 {result.matched} / {result.expectedCount} 个原文词 · 录音 {result.duration} 秒</p>{!result.transcript&&<p>没有识别到有效英语，建议检查麦克风音量后重录。</p>}<p className="score-note">只比较识别文本和原文，不评价音素、口音或音色。识别错误也会影响分数，请回听核对。</p><details><summary>查看识别文本与差异</summary><p className="transcript">{result.transcript||'（未识别到内容）'}</p>{result.details.length?<ul>{result.details.map((d,i)=><li key={i}>{d.kind==='missing'?`未匹配：${d.expected}`:d.kind==='extra'?`识别多出：${d.heard}`:`原文 ${d.expected} → 识别为 ${d.heard}`}</li>)}</ul>:<p>识别文本与原文匹配。</p>}</details></div>}
 {history.length>0&&<details className="reading-history"><summary>历次朗读记录（{history.length} 次）</summary>{history.slice().reverse().map(r=><div key={r.id}><p>{new Date(r.createdAt).toLocaleString('zh-CN')} · {r.score} 分</p><audio controls preload="none" src={r.audioUrl} className="article-audio" aria-label="回听历史朗读"/></div>)}</details>}
 </section>;
}
