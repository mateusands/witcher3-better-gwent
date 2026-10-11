import struct,sys
class CR2W:
    def __init__(s,d):
        s.d=d; t=[struct.unpack('<III',d[0x28+12*i:0x28+12*i+12]) for i in range(10)]
        so,sc,_=t[0]; no,nc,_=t[1]
        strs=d[so:so+sc]
        s.names=[]
        for i in range(nc):
            off,h=struct.unpack('<II',d[no+8*i:no+8*i+8]); s.names.append(strs[off:strs.index(b'\0',off)].decode())
        co,cc,_=t[4]
        s.chunks=[]
        for i in range(cc):
            cls,fl,par,sz,off,tpl,crc=struct.unpack('<HHIIIII',d[co+24*i:co+24*i+24]); s.chunks.append((s.names[cls],sz,off))
    def props(s,p):
        out={}
        while True:
            if p+4>len(s.d): return out,p
            n,t=struct.unpack('<HH',s.d[p:p+4])
            if n==0: return out,p+2
            sz=struct.unpack('<I',s.d[p+4:p+8])[0]
            out[s.names[n]]=s.val(s.names[t],p+8,p+4+sz)
            p=p+4+sz
    def val(s,t,p,end):
        d=s.d
        if t=='Float': return struct.unpack('<f',d[p:p+4])[0]
        if t in('Int32','Uint32'): return struct.unpack('<i',d[p:p+4])[0]
        if t=='Bool': return d[p]!=0
        if t=='CName': return s.names[struct.unpack('<H',d[p:p+2])[0]]
        if t=='TagList':
            c=d[p]; return [s.names[struct.unpack('<H',d[p+1+2*i:p+3+2*i])[0]] for i in range(c)]
        if t.startswith('array:'):
            et=t.split(',',2)[2]; c=struct.unpack('<I',d[p:p+4])[0]; q=p+4; arr=[]
            for i in range(c):
                if et in('CName',): arr.append(s.names[struct.unpack('<H',d[q:q+2])[0]]); q+=2
                elif et.startswith(('ptr:','handle:')) or et in ('Int32','Uint32','Float'): arr.append(struct.unpack('<i',d[q:q+4])[0]); q+=4
                else:
                    v,q=s.props(q+1) if d[q]==0 else s.props(q); arr.append(v)
            return arr
        if t and (t in ('Vector','EulerAngles') or t[0]=='S'):
            v,_=s.props(p+1 if d[p]==0 else p); return v
        return d[p:end].hex()
    def root(s):
        cls,sz,off=s.chunks[0]; v,_=s.props(off+1 if s.d[off]==0 else off); return v
if __name__=='__main__':
    import json
    r=CR2W(open(sys.argv[1],'rb').read()).root()
    print(json.dumps(r,indent=1)[:3000])
