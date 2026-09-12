'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Volume2, Pause, Play, Square, LoaderCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export type DictionaryEntry = {word:string;meaning:string};
type Result = DictionaryEntry & {source:string};
const results = new Map<string,Result>();
const requests = new Map<string,Promise<Result>>();
async function lookup(word:string):Promise<Result> {
 const k=word.toLowerCase(); if(results.has(k))return results.get(k)!;
 if(requests.has(k))return requests.get(k)!;
 const request=(async()=>{const r=await fetch('/api/lookup',{method:'POST',headers:{'Content-Type':'application/json','X-Local-App':'vocab'},body:JSON.stringify({word:k})});const value=await r.json() as Result & {error?:string};if(!r.ok)throw Error(value.error||'查询失败，请重试');results.set(k,value);return value;})();
 requests.set(k,request);try{return await request;}finally{requests.delete(k);}
}
export function spellingForms(word:string):string[]{return word.split('/').flatMap(w=>/\([a-z]+\)/i.test(w)?[w.replace(/\([a-z]+\)/gi,''),w.replace(/[()]/g,'')]:[w]).filter(Boolean);}
export default function ArticleReader({articleId,body,targets,dictionary}:{articleId:string;body:string;targets:DictionaryEntry[];dictionary:Map<string,DictionaryEntry>}) {
 const [voices,setVoices]=useState<SpeechSynthesisVoice[]>([]),[voice,setVoice]=useState(''),[rate,setRate]=useState('0.9');
 const [playback,setPlayback]=useState<'idle'|'starting'|'playing'|'paused'>('idle'),[speechError,setSpeechError]=useState('');
 const [supported,setSupported]=useState(false),[query,setQuery]=useState(''),[result,setResult]=useState<Result|null>(null),[lookupError,setLookupError]=useState(''),[loading,setLoading]=useState(false);
 const audioRef=useRef<HTMLAudioElement|null>(null); const [audioUrl,setAudioUrl]=useState('');
 const sequence=useRef(0),lookupSequence=useRef(0),ownSpeech=useRef(false),utterances=useRef<SpeechSynthesisUtterance[]>([]);
 const targetMap=useMemo(()=>new Map(targets.flatMap(w=>spellingForms(w.word).map(f=>[f.toLowerCase(),w] as const))),[targets]);
 const paragraphs=useMemo(()=>body.split(/\n+/).map(p=>p.split(/([A-Za-z]+(?:['’\-][A-Za-z]+)*)/g)),[body]);
 useEffect(()=>{
  const synth='speechSynthesis' in window?window.speechSynthesis:null;setSupported(!!synth);
  const update=()=>{const v=(synth?.getVoices()||[]).filter(v=>/^en([-_]|$)/i.test(v.lang));setVoices(v);setVoice(old=>v.some(x=>x.voiceURI===old)?old:(v.find(x=>x.localService)?.voiceURI||v[0]?.voiceURI||''));};update();synth?.addEventListener('voiceschanged',update);
  const stop=()=>{sequence.current++;if(ownSpeech.current)synth?.cancel();if(audioRef.current){audioRef.current.pause();audioRef.current.currentTime=0;}ownSpeech.current=false;utterances.current=[];setPlayback('idle');};
  window.addEventListener('vocab-stop-speech',stop);
  return()=>{stop();lookupSequence.current++;synth?.removeEventListener('voiceschanged',update);window.removeEventListener('vocab-stop-speech',stop);};
 },[]);
 function stop(){window.dispatchEvent(new Event('vocab-stop-speech'));}
 async function localAudio(){
  stop();setSpeechError('');setPlayback('starting');const token=sequence.current;
  try{let url=audioUrl;if(!url){const r=await fetch('/api/speech',{method:'POST',headers:{'Content-Type':'application/json','X-Local-App':'vocab'},body:JSON.stringify({articleId})});const value=await r.json() as {url:string;error?:string};if(!r.ok)throw Error(value.error||'生成音频失败');url=value.url;setAudioUrl(url);}
   if(token!==sequence.current)return;const audio=audioRef.current!;audio.src=url;audio.playbackRate=Number(rate);await audio.play();
  }catch(e){if(token===sequence.current){setPlayback('idle');setSpeechError(e instanceof Error?e.message:'音频未能播放，请点击下方播放器。');}}
 }
 async function speak(){
  if(audioUrl){const a=audioRef.current!;if(!a.paused){a.pause();return;}a.playbackRate=Number(rate);try{await a.play();}catch{setSpeechError('请点击下方音频播放器播放。');}return;}
  if(!supported){await localAudio();return;}
  if(playback==='paused'){window.speechSynthesis.resume();setPlayback('playing');return;}
  if(playback==='playing'){window.speechSynthesis.pause();setPlayback('paused');return;}
  stop();setSpeechError('');const synth=window.speechSynthesis;
  const available=synth.getVoices().filter(v=>/^en([-_]|$)/i.test(v.lang));
  if(!available.length){await localAudio();return;}
  const chosen=available.find(v=>v.voiceURI===voice)||available.find(v=>v.localService)||available[0];
  const chunks=body.match(/[^.!?]+(?:[.!?]+|$)/g)||[body];const token=++sequence.current;
  ownSpeech.current=true;setPlayback('starting');
  utterances.current=chunks.map((chunk,i)=>{const u=new SpeechSynthesisUtterance(chunk);u.lang=chosen.lang;u.voice=chosen;u.rate=Number(rate);
   u.onstart=()=>{if(sequence.current===token)setPlayback('playing');};
   u.onend=()=>{if(sequence.current===token&&i===chunks.length-1){ownSpeech.current=false;setPlayback('idle');utterances.current=[];}};
   u.onerror=e=>{if(sequence.current!==token)return;sequence.current++;ownSpeech.current=false;synth.cancel();setPlayback('idle');if(e.error!=='canceled'&&e.error!=='interrupted')setSpeechError('朗读未能播放（'+e.error+'），请检查英语语音和电脑音量，或换系统浏览器。');};return u;});
  utterances.current.forEach(u=>synth.speak(u));
 }
 async function queryWord(word:string){
  const token=++lookupSequence.current;setQuery(word);setResult(null);setLookupError('');
  const k=word.toLowerCase().replaceAll('’',"'");const local=targetMap.get(k)||dictionary.get(k);
  if(local){setLoading(false);setResult({...local,source:'本地词库'});return;}
  setLoading(true);try{const r=await lookup(k);if(token===lookupSequence.current)setResult(r);}catch(e){if(token===lookupSequence.current)setLookupError(e instanceof Error?e.message:'查询失败');}finally{if(token===lookupSequence.current)setLoading(false);}
 }
 return <>
  <div className="reader-toolbar"><Button variant="outline" onClick={speak} disabled={playback==='starting'} aria-label={playback==='playing'?'暂停朗读':playback==='paused'?'继续朗读':'朗读文章'}>{playback==='starting'?<LoaderCircle className="spin"/>:playback==='playing'?<Pause/>:playback==='paused'?<Play/>:<Volume2/>}{playback==='starting'?'准备播放':playback==='playing'?'暂停朗读':playback==='paused'?'继续朗读':'朗读文章'}</Button><Button variant="ghost" aria-label="停止朗读" onClick={stop} disabled={playback==='idle'}><Square/>停止</Button>
   <Select value={rate} onValueChange={v=>v&&setRate(v)} disabled={playback!=='idle'}><SelectTrigger aria-label="朗读速度"><SelectValue>{rate}×</SelectValue></SelectTrigger><SelectContent>{['0.7','0.9','1','1.2'].map(r=><SelectItem key={r} value={r}>{r}×</SelectItem>)}</SelectContent></Select>
   {voices.length>0&&<Select value={voice} onValueChange={v=>v&&setVoice(v)} disabled={playback!=='idle'}><SelectTrigger className="voice-picker" aria-label="英语语音"><SelectValue>{voices.find(v=>v.voiceURI===voice)?.name||'英语语音'}</SelectValue></SelectTrigger><SelectContent>{voices.map(v=><SelectItem key={v.voiceURI} value={v.voiceURI}>{v.name} ({v.lang})</SelectItem>)}</SelectContent></Select>}
  </div><p className="reader-hint" role="status">{speechError|| (playback==='playing'?'正在朗读 · 点击暂停可暂时停下':playback==='paused'?'朗读已暂停':'点击任意英文单词查中文释义 · 本地未收录时按需调用 API 并缓存')}</p>
  <audio ref={audioRef} controls={!!audioUrl} hidden={!audioUrl} className="article-audio" preload="none" onPlay={()=>{ownSpeech.current=true;setPlayback('playing');}} onPause={()=>setPlayback(p=>p==='idle'?'idle':'paused')} onEnded={()=>{ownSpeech.current=false;setPlayback('idle');}} onError={()=>{setPlayback('idle');setSpeechError('音频加载失败，请刷新页面重试。');}}/>
  <div className="story-body">{paragraphs.map((parts,i)=><p key={i}>{parts.map((part,j)=>/^[A-Za-z]/.test(part)?<button key={j} type="button" className={'lookup-word'+(targetMap.has(part.toLowerCase())?' target-word':'')} title={targetMap.get(part.toLowerCase())?.meaning} aria-label={`查询 ${part} 的意思`} onClick={()=>queryWord(part)}>{part}</button>:part)}</p>)}</div>
  <Dialog open={!!query} onOpenChange={open=>{if(!open){lookupSequence.current++;setQuery('');}}}><DialogContent className="word-lookup-dialog"><DialogHeader><DialogTitle>{query}</DialogTitle><DialogDescription>单词释义</DialogDescription></DialogHeader>{loading?<p role="status"><LoaderCircle className="spin inline"/> 本地未收录，正在查询…</p>:lookupError?<><p role="alert">{lookupError}</p><Button variant="outline" onClick={()=>queryWord(query)}>重试查询</Button></>:result?<><p className="lookup-meaning">{result.meaning}</p><p className="reader-hint">{result.word!==query.toLowerCase()?`词条：${result.word} · `:''}{result.source} · 通用释义，请结合上下文理解</p></>:null}</DialogContent></Dialog>
 </>;
}
