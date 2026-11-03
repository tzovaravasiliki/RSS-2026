"""Fixed-endpoint provider adapters, explicit opt-in, one attempt, no secret logging."""
import json
import os
import re
import urllib.error
import urllib.request
import contracts

KEYS={'openai':'OPENAI_API_KEY','anthropic':'ANTHROPIC_API_KEY','gemini':'GEMINI_API_KEY'}


class ProviderError(ValueError):
    pass


def read_key(provider):
    name=KEYS[provider]
    value=os.environ.get(name,'').strip()
    if not value and os.name=='nt':
        # Read the persisted USER variable even when VS Code inherited an old environment.
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as h:
                value=str(winreg.QueryValueEx(h,name)[0]).strip()
        except OSError:
            pass
    return value


def key_status():
    return {p:{'variable':name,'available':bool(read_key(p))} for p,name in KEYS.items()}


def build(profile, public, max_tokens=3000):
    provider,model=profile['provider'],profile['model']
    if provider not in KEYS or not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}',model):
        raise ValueError('Unsupported provider or invalid model ID')
    text=json.dumps(public,ensure_ascii=False)
    schema=contracts.schema(public)
    if provider=='openai':
        url='https://api.openai.com/v1/responses'
        body={'model':model,'store':False,'instructions':contracts.PROMPT,'input':text,
            'max_output_tokens':max_tokens,'text':{'format':{'type':'json_schema',
            'name':'team_coordination','strict':True,'schema':schema}}}
        if model.startswith('gpt-5'):
            body['reasoning']={'effort':'low'}
    elif provider=='anthropic':
        url='https://api.anthropic.com/v1/messages'
        body={'model':model,'max_tokens':max_tokens,'system':contracts.PROMPT,
            'messages':[{'role':'user','content':text}],
            'output_config':{'format':{'type':'json_schema','schema':schema}}}
    else:
        url='https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent'
        body={'contents':[{'role':'user','parts':[{'text':text}]}],
            'systemInstruction':{'parts':[{'text':contracts.PROMPT}]},
            'generationConfig':{'maxOutputTokens':max_tokens,'responseMimeType':'application/json',
                                'responseJsonSchema':schema}}
    return url,body


def parse(provider,response):
    if provider=='openai':
        if response.get('status')!='completed':
            raise ProviderError('OpenAI response incomplete/failed; no decision executed')
        blocks=[c for item in response.get('output',[]) for c in item.get('content',[])]
        if any(c.get('type')=='refusal' for c in blocks):
            raise ProviderError('OpenAI refusal; no decision executed')
        text=''.join(c.get('text','') for c in blocks if c.get('type')=='output_text')
        usage=response.get('usage',{})
        metrics={'input_tokens':usage.get('input_tokens',0),'output_tokens':usage.get('output_tokens',0),
                 'cached_input_tokens':usage.get('input_tokens_details',{}).get('cached_tokens',0)}
        model=response.get('model')
    elif provider=='anthropic':
        if response.get('stop_reason')!='end_turn':
            raise ProviderError('Claude response did not finish normally; no decision executed')
        text=''.join(b.get('text','') for b in response.get('content',[]) if b.get('type')=='text')
        usage=response.get('usage',{})
        metrics={'input_tokens':usage.get('input_tokens',0),'output_tokens':usage.get('output_tokens',0),
                 'cached_input_tokens':usage.get('cache_read_input_tokens',0),
                 'cache_creation_input_tokens':usage.get('cache_creation_input_tokens',0)}
        model=response.get('model')
    else:
        candidates=response.get('candidates',[])
        if len(candidates)!=1 or candidates[0].get('finishReason')!='STOP':
            raise ProviderError('Gemini response blocked/incomplete; no decision executed')
        text=''.join(b.get('text','') for b in candidates[0].get('content',{}).get('parts',[]) if not b.get('thought'))
        usage=response.get('usageMetadata',{})
        metrics={'input_tokens':usage.get('promptTokenCount',0),'output_tokens':usage.get('candidatesTokenCount',0),
                 'cached_input_tokens':usage.get('cachedContentTokenCount',0),
                 'reasoning_tokens':usage.get('thoughtsTokenCount',0)}
        model=response.get('modelVersion')
    if not text:
        raise ProviderError('No output text; no decision executed')
    try:
        raw=json.loads(text)
    except ValueError:
        raise ProviderError('Output is not valid JSON; no decision executed') from None
    return raw,metrics,model


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def infer(profile,public,max_tokens=3000,transport=None):
    key=read_key(profile['provider'])
    if not key:
        raise ProviderError(KEYS[profile['provider']]+' is missing')
    url,body=build(profile,public,max_tokens)
    headers={'Content-Type':'application/json'}
    if profile['provider']=='openai':
        headers['Authorization']='Bearer '+key
    elif profile['provider']=='anthropic':
        headers.update({'x-api-key':key,'anthropic-version':'2023-06-01'})
    else:
        headers['x-goog-api-key']=key
    req=urllib.request.Request(url,data=json.dumps(body).encode(),headers=headers,method='POST')
    try:
        opener=transport or urllib.request.build_opener(NoRedirect()).open
        with opener(req,timeout=60) as r:
            content=r.read(8*1024*1024+1)
            if len(content)>8*1024*1024:
                raise ProviderError('Provider response exceeds size limit')
            response=json.loads(content)
    except urllib.error.HTTPError as e:
        tips={400:'Model/schema/settings rejected',401:'Key rejected',403:'Access denied',404:'Model unavailable',429:'Quota or rate limit'}
        raise ProviderError(f'HTTP {e.code}: '+tips.get(e.code,'Provider error')+'. No automatic retry.') from None
    except (urllib.error.URLError,TimeoutError,OSError):
        raise ProviderError('Network/timeout failure; the request may have been billed. No retry.') from None
    except ValueError as e:
        if isinstance(e,ProviderError):
            raise
        raise ProviderError('Provider returned invalid JSON') from None
    raw,usage,returned=parse(profile['provider'],response)
    return {'output':raw,'usage':usage,'returned_model':returned,'response_id':response.get('id',response.get('responseId')),
            'native_usage':response.get('usage',response.get('usageMetadata',{})),
            'request_sha256':contracts.digest({'url':url,'body':body})}
