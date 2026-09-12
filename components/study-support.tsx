'use client';
import {useState} from 'react';
import {Button} from '@/components/ui/button';
import RetellingPractice, {type Retelling} from '@/components/retelling-practice';
import ArticleReader from '@/components/article-reader';
import {Input} from '@/components/ui/input';
export type Source={retellings?:Retelling[];retellHint?:string;id:string;publisher:string;title:string;url:string;quote:string;translation:string;phrase:string;note:string;verifiedAt:string;match:string};
export type Coach={summary:string;items:{original:string;suggestion:string;reason:string}[]};
function Excerpt({source:s,repeated,articleId,onSaved}:{source:Source;repeated:boolean;articleId:string;onSaved:()=>Promise<unknown>}){
 const [practice,setPractice]=useState(false),[answer,setAnswer]=useState(''),[checked,setChecked]=useState(false);
 const correct=answer.trim().toLowerCase().replace(/\s+/g,' ')===s.phrase.toLowerCase();
 return <div className="authentic-excerpt"><div className="source-meta">{s.publisher} · {s.match}{repeated?' · 档案中已出现':''}</div>
 <ArticleReader articleId="" sourceId={s.id} body={s.quote} targets={[]} dictionary={new Map()} controlsOnly/><blockquote lang="en">{practice?s.quote.replace(s.phrase,'________'):s.quote}</blockquote>
 {!practice&&<><p>{s.translation}</p><p><strong>{s.phrase}</strong> · {s.note}</p></>}
 <a href={s.url} target="_blank" rel="noopener noreferrer">阅读原文：{s.title} ↗</a>
 <div className="phrase-actions"><Button variant="outline" onClick={()=>{setPractice(!practice);setChecked(false);setAnswer('');}}>{practice?'返回原句':'遮住搭配，练习回忆'}</Button>
 {practice&&<><Input aria-label={'填写搭配 '+s.title} value={answer} onChange={e=>{setAnswer(e.target.value);setChecked(false);}} placeholder="填写缺少的英语搭配"/><Button variant="outline" onClick={()=>setChecked(true)}>核对答案</Button></>}</div>
 {practice&&checked&&<p role="status">{correct?'答对了！':`参考答案：${s.phrase}`} · {s.translation}</p>}
 <RetellingPractice articleId={articleId} sourceId={s.id} original={s.quote} hint={s.retellHint||s.translation} history={s.retellings} onSaved={onSaved}/>
 </div>;
}
export default function StudySupport({articleId,sources,coach,seen,onSaved}:{articleId:string;sources:Source[];coach?:Coach;seen:string[];onSaved:()=>Promise<unknown>}){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState<Coach|undefined>(coach);
 async function check(){setBusy(true);setError('');try{const r=await fetch('/api/coach',{method:'POST',headers:{'Content-Type':'application/json','X-Local-App':'vocab'},body:JSON.stringify({articleId})});const value=await r.json() as Coach & {error?:string};if(!r.ok)throw Error(value.error||'检查失败');setResult(value);await onSaved();}catch(e){setError(e instanceof Error?e.message:'检查失败');}finally{setBusy(false);}}
 return <section className="study-support"><h4>真实语料对照</h4><p className="score-note">从已核对的 BBC / British Council 小语料库选取两条短摘录，学习自然搭配。不是本篇故事的来源；语料有限，会重复用于复习。</p>
 {sources.map(s=><Excerpt key={s.id} articleId={articleId} onSaved={onSaved} source={s} repeated={seen.includes(s.id)}/>)}
 <details className="coach-panel"><summary>表达检查与改写建议</summary><p>AI 建议供参考，可同时核对上方真实语料。原文及词频统计保持留档。</p>
 {!result&&<Button variant="outline" disabled={busy} onClick={check}>{busy?'正在检查表达…':'检查本篇表达（调用已配置 API）'}</Button>}
 {error&&<p role="alert">{error}</p>}{result&&<><p>{result.summary}</p>{result.items.map((item,i)=><div className="coach-item" key={i}><p><strong>原句</strong> <span lang="en">{item.original}</span></p><p><strong>建议</strong> <span lang="en">{item.suggestion}</span></p><p>{item.reason}</p></div>)}<small>检查结果已保存，重新打开无需重复调用 API。</small></>}
 </details></section>;
}
