import test from 'node:test';import assert from 'node:assert/strict';
import {syncVault} from './client/vault.mjs';
test('GitHub PUT 404 is an error, not a successful synchronization',async()=>{
 const saved=globalThis.fetch;let n=0;globalThis.fetch=async()=>{n++;return n===1?new Response(JSON.stringify({private:true,default_branch:'main'}),{status:200}):new Response('{}',{status:404});};
 try{await assert.rejects(()=>syncVault({repo:'test/repo',vault:'a'.repeat(32),token:'synthetic',password:'synthetic-password'}, {format:'next-song-mobile',version:1,source_id:'a'.repeat(32),created_at:'2026-10-18T00:00:00Z',tracks:[],queue:[],friends:[]},[]),/GitHub 404/);assert.equal(n,3);}finally{globalThis.fetch=saved;}
});
