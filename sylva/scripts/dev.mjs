import { spawn } from 'node:child_process';
const processes = [spawn(process.execPath, ['api/server.mjs'], {stdio:'inherit'}), spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '0.0.0.0'], {stdio:'inherit'})];
for (const signal of ['SIGINT','SIGTERM']) process.on(signal, () => { processes.forEach(p=>p.kill(signal)); process.exit(); });
processes.forEach(p=>p.on('exit',code=>{if(code){processes.forEach(other=>other.kill());process.exit(code);}}));
