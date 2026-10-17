import ts from 'typescript';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const project=path.resolve(process.argv[2]);
const configPath=path.join(path.dirname(project),'tsconfig.json');
const config=ts.readConfigFile(configPath,ts.sys.readFile);
const parsed=ts.parseJsonConfigFileContent(config.config,ts.sys,path.dirname(configPath),{
  baseUrl:root,
  paths:{'@motion-canvas/*':['node_modules/@motion-canvas/*'],'vite/*':['node_modules/vite/*']},
  typeRoots:[path.join(root,'node_modules'),path.join(root,'node_modules/@types')],
});
const program=ts.createProgram(parsed.fileNames,parsed.options);
const diagnostics=[...parsed.errors,...ts.getPreEmitDiagnostics(program)];
if(diagnostics.length){
  console.error(ts.formatDiagnosticsWithColorAndContext(diagnostics,{
    getCanonicalFileName:f=>f,getCurrentDirectory:()=>root,getNewLine:()=> '\n',
  }));process.exitCode=1;
}else console.log('Motion Canvas project type check passed.');
