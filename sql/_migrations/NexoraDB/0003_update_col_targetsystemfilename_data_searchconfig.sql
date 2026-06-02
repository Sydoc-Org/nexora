update SearchConfig set col_targetsystemfilename = 'FileName' where ProcessName in ('elektromaterial.02_Invoice', 'privera.03_Invoice_New')
update SearchConfig set col_targetsystemfilename = 'init_Name' where ProcessName = 'privera.02_InitialScan'
update SearchConfig set col_targetsystemfilename = 'FilenamePDF' where ProcessName = 'privera.02_Posteingang'
