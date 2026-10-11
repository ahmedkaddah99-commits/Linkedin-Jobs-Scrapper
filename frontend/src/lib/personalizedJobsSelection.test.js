import assert from 'node:assert/strict';
import test from 'node:test';
import { hasSelectedJobFunction } from './personalizedJobsApi.js';
test('feed requires a nonempty Job Function',()=>{
 for(const role of [undefined,[],['','  '],''])assert.equal(hasSelectedJobFunction({role}),false);
 for(const role of [['Data Analyst'],[' ','Software Engineer'],'Business Analyst'])assert.equal(hasSelectedJobFunction({role}),true);
});
