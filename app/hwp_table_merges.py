"""Explicit source-declared straight table spans; never infer merged cells."""


def validated_merges(matrix, merges):
    rows=len(matrix);cols=len(matrix[0]) if rows else 0
    if not rows or not cols or any(len(row)!=cols for row in matrix):
        raise ValueError("MERGE_MATRIX_NOT_RECTANGULAR")
    occupied=set();result=[]
    for merge in merges:
        if not isinstance(merge,(list,tuple)) or len(merge)!=4 or any(type(v) is not int for v in merge):
            raise ValueError("MERGE_REQUIRES_ROW_COL_HEIGHT_WIDTH")
        r,c,height,width=merge
        if r<0 or c<0 or height<1 or width<1 or r+height>rows or c+width>cols:
            raise ValueError("MERGE_OUT_OF_BOUNDS")
        if height==width==1 or height>1 and width>1:
            raise ValueError("MERGE_ONLY_NONTRIVIAL_STRAIGHT_SPANS")
        cells={(y,x) for y in range(r,r+height) for x in range(c,c+width)}
        if occupied.intersection(cells):raise ValueError("MERGE_OVERLAP")
        if any(matrix[y][x] not in ("",[]) for y,x in cells-{(r,c)}):
            raise ValueError("MERGE_WOULD_LOSE_COVERED_CONTENT")
        occupied.update(cells);result.append(tuple(merge))
    return sorted(result,reverse=True)


def apply_native_merges(hwp,matrix,merges,go_to_cell):
    spans=validated_merges(matrix,merges);actions=[]
    for r,c,height,width in spans:
        go_to_cell(r,c)
        names=['TableCellBlock','TableCellBlockExtend']
        names+=['TableLowerCell']*(height-1)+['TableRightCell']*(width-1)
        names+=['TableMergeCell','Cancel']
        for name in names:
            value=getattr(hwp,name)()
            actions.append({'merge':[r,c,height,width],'action':name,'returned':value})
            if value is not True:raise RuntimeError('NATIVE_MERGE_ACTION_FAILED:'+name)
    return actions
